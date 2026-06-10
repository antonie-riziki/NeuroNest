import os
import sys
import glob
import getpass
import warnings
from typing import List, Union
from dotenv import load_dotenv
from langchain_community.document_loaders import PyPDFLoader, CSVLoader
from langchain_core.prompts import PromptTemplate
from langchain_classic.chains import RetrievalQA
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document

sys.path.insert(1, "./apps")


from .ingestion import load_model, load_documents
from .vector_store import create_vector_store
from .prompt_builder import prompt_template_func

warnings.filterwarnings("ignore")




def get_qa_chain(source_dir=None, use_global_db=False):
    """
    Create QA chain with proper error handling
    """

    try:
        from django.conf import settings
        llm, embeddings = load_model()
        if not llm or not embeddings:
            model_type = "gemini"
            raise ValueError(f"Model {model_type} not configured properly")

        vector_store = None
        if use_global_db:
            db_path = os.path.join(settings.BASE_DIR, 'vector_store_db')
            if not os.path.exists(db_path):
                raise ValueError("Global vector store not found. Please run 'python manage.py train_rag' first.")
            vector_store = FAISS.load_local(db_path, embeddings, allow_dangerous_deserialization=True)

        if source_dir:
            docs = load_documents(source_dir)
            if docs:
                text_splitter = RecursiveCharacterTextSplitter(chunk_size=10000, chunk_overlap=200)
                splits = text_splitter.split_documents(docs)
                if vector_store:
                    vector_store.add_documents(splits)
                else:
                    vector_store = FAISS.from_documents(splits, embeddings)
            elif not vector_store:
                raise ValueError("No documents found in the specified sources and no global db available.")

        if not vector_store:
             raise ValueError("Failed to initialize vector store: no global DB and no source documents provided.")

        retriever = vector_store.as_retriever(search_kwargs={"k": 5})

        prompt = PromptTemplate(
            template=prompt_template_func(), input_variables=["context", "question"]
        )

        response = RetrievalQA.from_chain_type(
            llm=llm,
            chain_type="stuff",
            retriever=retriever,
            return_source_documents=True,
            chain_type_kwargs={"prompt": prompt},
        )

        return response

    except Exception as e:
        print(f"Error initializing QA system: {e}")
        return f"Error initializing QA system: {e}"


def query_system(query: str, qa_chain):
    if not qa_chain:
        return "System not initialized properly"

    if isinstance(qa_chain, str):
        return qa_chain

    try:
        result = qa_chain({"query": query})
        if not result["result"] or "don't know" in result["result"].lower():
            return "The answer could not be found in the provided documents"
        return f"NIA: {result['result']} \nSources: {[s.metadata['source'] for s in result['source_documents']]}"
    except Exception as e:
        return f"Error processing query: {e}"



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




def get_qa_chain(source_dir=None, use_global_db=False, child_profile=None, caregiver_profile=None, child_id=None):
    """
    Create QA chain with proper error handling and personalization
    """

    try:
        from django.conf import settings
        llm, embeddings = load_model()
        if not llm or not embeddings:
            model_type = "gemini"
            raise ValueError(f"Model {model_type} not configured properly")

        vector_store = None
        global_db_path = os.path.join(settings.BASE_DIR, 'vector_store_db', 'global')
        os.makedirs(os.path.dirname(global_db_path), exist_ok=True)

        # 1. Initialize or load the global database
        if os.path.exists(global_db_path):
            vector_store = FAISS.load_local(global_db_path, embeddings, allow_dangerous_deserialization=True)
        else:
            global_docs_dir = os.path.join(settings.BASE_DIR, 'media', 'docs', 'global')
            os.makedirs(global_docs_dir, exist_ok=True)
            docs = load_documents(global_docs_dir)
            if not docs:
                docs = [Document(page_content="NIA Global Knowledge Base - Neurodevelopmental and neurodiversity support platform developed by Beyond Brain Barriers.", metadata={"source": "system"})]
            
            text_splitter = RecursiveCharacterTextSplitter(chunk_size=10000, chunk_overlap=200)
            splits = text_splitter.split_documents(docs)
            vector_store = FAISS.from_documents(splits, embeddings)
            vector_store.save_local(global_db_path)

        # 2. Load and merge child-specific database if in personalized mode
        if child_id:
            child_db_path = os.path.join(settings.BASE_DIR, 'vector_store_db', f'child_{child_id}')
            child_docs_dir = os.path.join(settings.BASE_DIR, 'media', 'docs', f'child_{child_id}')
            os.makedirs(child_docs_dir, exist_ok=True)
            
            child_vector_store = None
            if os.path.exists(child_db_path):
                child_vector_store = FAISS.load_local(child_db_path, embeddings, allow_dangerous_deserialization=True)
            else:
                docs = load_documents(child_docs_dir)
                if docs:
                    text_splitter = RecursiveCharacterTextSplitter(chunk_size=10000, chunk_overlap=200)
                    splits = text_splitter.split_documents(docs)
                    child_vector_store = FAISS.from_documents(splits, embeddings)
                    child_vector_store.save_local(child_db_path)

            if child_vector_store:
                # Merge child documents into our vector store retrieval context
                vector_store.merge_from(child_vector_store)

        # 3. Add dynamic source directory docs if passed directly
        if source_dir:
            docs = load_documents(source_dir)
            if docs:
                text_splitter = RecursiveCharacterTextSplitter(chunk_size=10000, chunk_overlap=200)
                splits = text_splitter.split_documents(docs)
                vector_store.add_documents(splits)

        retriever = vector_store.as_retriever(search_kwargs={"k": 5})

        prompt = PromptTemplate(
            template=prompt_template_func(child_profile, caregiver_profile),
            input_variables=["context", "question"]
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
        return f"NIA: {result['result']}"
    except Exception as e:
        return f"Error processing query: {e}"


def update_vector_store_for_child(child_id):
    """
    Rebuild the FAISS database for a specific child from their media files.
    """
    try:
        from django.conf import settings
        llm, embeddings = load_model()
        if not embeddings:
            return False

        child_db_path = os.path.join(settings.BASE_DIR, 'vector_store_db', f'child_{child_id}')
        child_docs_dir = os.path.join(settings.BASE_DIR, 'media', 'docs', f'child_{child_id}')
        os.makedirs(child_docs_dir, exist_ok=True)

        docs = load_documents(child_docs_dir)
        if docs:
            text_splitter = RecursiveCharacterTextSplitter(chunk_size=10000, chunk_overlap=200)
            splits = text_splitter.split_documents(docs)
            vector_store = FAISS.from_documents(splits, embeddings)
            vector_store.save_local(child_db_path)
            return True
    except Exception as e:
        print(f"Error updating child vector store: {e}")
    return False


def update_global_vector_store():
    """
    Rebuild the global FAISS database from media files.
    """
    try:
        from django.conf import settings
        llm, embeddings = load_model()
        if not embeddings:
            return False

        global_db_path = os.path.join(settings.BASE_DIR, 'vector_store_db', 'global')
        global_docs_dir = os.path.join(settings.BASE_DIR, 'media', 'docs', 'global')
        os.makedirs(global_docs_dir, exist_ok=True)

        docs = load_documents(global_docs_dir)
        if not docs:
            docs = [Document(page_content="NIA Global Knowledge Base - Neurodevelopmental and neurodiversity support platform developed by Beyond Brain Barriers.", metadata={"source": "system"})]
            
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=10000, chunk_overlap=200)
        splits = text_splitter.split_documents(docs)
        vector_store = FAISS.from_documents(splits, embeddings)
        vector_store.save_local(global_db_path)
        return True
    except Exception as e:
        print(f"Error updating global vector store: {e}")
    return False



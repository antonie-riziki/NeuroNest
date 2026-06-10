import os
from typing import List
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document


def create_vector_store(
    docs: List[Document], embeddings, chunk_size: int = 10000, chunk_overlap: int = 200
):
    """
    Create vector store from documents
    """
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size, chunk_overlap=chunk_overlap
    )
    splits = text_splitter.split_documents(docs)

    return FAISS.from_documents(splits, embeddings).as_retriever(search_kwargs={"k": 5})
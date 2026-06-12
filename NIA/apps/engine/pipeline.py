import os
import sys
import warnings
from typing import Iterable, List, Union
from dotenv import load_dotenv
from langchain_community.document_loaders import PyPDFLoader, CSVLoader
from langchain_core.prompts import PromptTemplate
from langchain_core.retrievers import BaseRetriever
from langchain_classic.chains import RetrievalQA
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document

sys.path.insert(1, "./apps")


from .ingestion import load_model, load_documents
from .prompt_builder import prompt_template_func

warnings.filterwarnings("ignore")


def _knowledge_source_dirs(settings):
    """Return every directory that should seed the global RAG knowledge base."""
    candidate_dirs = [
        os.path.join(settings.BASE_DIR, 'media', 'docs', 'global'),
        os.path.join(settings.BASE_DIR, 'static', 'docs'),
    ]
    return [path for path in candidate_dirs if os.path.isdir(path)]


def _load_documents_from_dirs(source_dirs: Iterable[str]):
    docs = []
    for source_dir in source_dirs:
        docs.extend(load_documents(source_dir))
    return docs


def _vector_store_is_stale(db_path: str, source_dirs: Iterable[str]) -> bool:
    index_file = os.path.join(db_path, 'index.faiss')
    if not os.path.exists(index_file):
        return True
    index_mtime = os.path.getmtime(index_file)
    for source_dir in source_dirs:
        for root, _dirs, files in os.walk(source_dir):
            for file_name in files:
                if os.path.splitext(file_name)[1].lower() in {'.pdf', '.csv', '.docx', '.doc', '.dot'}:
                    if os.path.getmtime(os.path.join(root, file_name)) > index_mtime:
                        return True
    return False


_VECTOR_STORE_CACHE = {}
_CHUNK_SIZE = 2000
_CHUNK_OVERLAP = 200
_RETRIEVAL_K = 4

def _write_index_version(db_path):
    pass # Placeholder if needed

def get_qa_chain(source_dir=None, use_global_db=False, child_profile=None, caregiver_profile=None, child_id=None, conversation_history=None, audience="caregiver"):
    """
    Create QA chain with high-performance in-memory caching.
    """
    try:
        from django.conf import settings
        llm, embeddings = load_model()
        if not llm or not embeddings:
            raise ValueError("Model or embeddings not configured properly")

        global_db_path = os.path.join(settings.BASE_DIR, 'vector_store_db', 'global')
        source_dirs = _knowledge_source_dirs(settings)

        # 1. Initialize or load the global database into cache
        if "global" not in _VECTOR_STORE_CACHE:
            os.makedirs(os.path.join(settings.BASE_DIR, 'media', 'docs', 'global'), exist_ok=True)
            if os.path.exists(global_db_path) and not _vector_store_is_stale(global_db_path, source_dirs):
                _VECTOR_STORE_CACHE["global"] = FAISS.load_local(global_db_path, embeddings, allow_dangerous_deserialization=True)
            else:
                docs = _load_documents_from_dirs(source_dirs)
                if not docs:
                    docs = [Document(page_content="NIA Global Knowledge Base - Neurodevelopmental and neurodiversity support platform.", metadata={"source": "system"})]
                
                text_splitter = RecursiveCharacterTextSplitter(chunk_size=_CHUNK_SIZE, chunk_overlap=_CHUNK_OVERLAP)
                splits = text_splitter.split_documents(docs)
                vector_store = FAISS.from_documents(splits, embeddings)
                vector_store.save_local(global_db_path)
                _VECTOR_STORE_CACHE["global"] = vector_store
                
        vector_store = _VECTOR_STORE_CACHE["global"]

        # 2. Load and merge child-specific database if in personalized mode
        if child_id:
            child_db_path = os.path.join(settings.BASE_DIR, 'vector_store_db', f'child_{child_id}')
            child_docs_dir = os.path.join(settings.BASE_DIR, 'media', 'docs', f'child_{child_id}')
            os.makedirs(child_docs_dir, exist_ok=True)

            child_cache_key = f"child_{child_id}"
            
            if child_cache_key not in _VECTOR_STORE_CACHE:
                if os.path.exists(child_db_path) and not _vector_store_is_stale(child_db_path, [child_docs_dir]):
                    _VECTOR_STORE_CACHE[child_cache_key] = FAISS.load_local(child_db_path, embeddings, allow_dangerous_deserialization=True)
                else:
                    docs = load_documents(child_docs_dir)
                    if docs:
                        text_splitter = RecursiveCharacterTextSplitter(chunk_size=_CHUNK_SIZE, chunk_overlap=_CHUNK_OVERLAP)
                        splits = text_splitter.split_documents(docs)
                        child_vs = FAISS.from_documents(splits, embeddings)
                        child_vs.save_local(child_db_path)
                        _VECTOR_STORE_CACHE[child_cache_key] = child_vs
                    else:
                        _VECTOR_STORE_CACHE[child_cache_key] = None

            child_vector_store = _VECTOR_STORE_CACHE[child_cache_key]

            if child_vector_store:
                merged_cache_key = f"merged_{child_id}"
                if merged_cache_key not in _VECTOR_STORE_CACHE:
                    # Load a fresh copy of global from disk to merge into safely without mutating the shared global cache
                    merged_vs = FAISS.load_local(global_db_path, embeddings, allow_dangerous_deserialization=True)
                    merged_vs.merge_from(child_vector_store)
                    _VECTOR_STORE_CACHE[merged_cache_key] = merged_vs
                
                vector_store = _VECTOR_STORE_CACHE[merged_cache_key]

        # 3. Add dynamic source directory docs if passed directly
        if source_dir:
            docs = load_documents(source_dir)
            if docs:
                text_splitter = RecursiveCharacterTextSplitter(chunk_size=_CHUNK_SIZE, chunk_overlap=_CHUNK_OVERLAP)
                splits = text_splitter.split_documents(docs)
                vector_store.add_documents(splits)

        retriever = vector_store.as_retriever(search_kwargs={"k": _RETRIEVAL_K})

        prompt = PromptTemplate(
            template=prompt_template_func(child_profile, caregiver_profile, conversation_history, audience),
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
            return "I don't have enough information to answer confidently yet. Could you tell me a little more about what is happening?"
        return result['result']
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
            text_splitter = RecursiveCharacterTextSplitter(chunk_size=_CHUNK_SIZE, chunk_overlap=_CHUNK_OVERLAP)
            splits = text_splitter.split_documents(docs)
            vector_store = FAISS.from_documents(splits, embeddings)
            vector_store.save_local(child_db_path)
            
            # Clear cache for this child so it gets reloaded
            _VECTOR_STORE_CACHE.pop(f"child_{child_id}", None)
            _VECTOR_STORE_CACHE.pop(f"merged_{child_id}", None)
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

        docs = _load_documents_from_dirs(_knowledge_source_dirs(settings))
        if not docs:
            docs = [Document(page_content="NIA Global Knowledge Base - Neurodevelopmental and neurodiversity support platform developed by Beyond Brain Barriers.", metadata={"source": "system"})]

        text_splitter = RecursiveCharacterTextSplitter(chunk_size=_CHUNK_SIZE, chunk_overlap=_CHUNK_OVERLAP)
        splits = text_splitter.split_documents(docs)
        vector_store = FAISS.from_documents(splits, embeddings)
        vector_store.save_local(global_db_path)
        
        # Clear global cache
        _VECTOR_STORE_CACHE.clear()
        return True
    except Exception as e:
        print(f"Error updating global vector store: {e}")
    return False



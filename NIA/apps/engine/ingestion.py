import os
import sys
import glob
import getpass
import warnings


sys.path.insert(1, "./apps")

from dotenv import load_dotenv, find_dotenv
from langchain_community.document_loaders import PyPDFLoader, CSVLoader, Docx2txtLoader, UnstructuredWordDocumentLoader
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings


warnings.filterwarnings("ignore")


load_dotenv(find_dotenv())

GEMINI_API_KEY = os.environ.get("GOOGLE_API_KEY")

if not GEMINI_API_KEY:
    GEMINI_API_KEY = getpass.getpass("Enter you Google Gemini API key: ")





def load_model():
    """
    Func loads the model and embeddings
    """
    model = ChatGoogleGenerativeAI(
        model="gemini-3.1-flash-lite",
        google_api_key=GEMINI_API_KEY,
        temperature=0.4,
        convert_system_message_to_human=True,
    )
    embeddings = GoogleGenerativeAIEmbeddings(
        model="gemini-embedding-2",
        google_api_key=GEMINI_API_KEY,
    )
    return model, embeddings


def load_documents(source_dir: str):
    """
    Load documents from multiple sources recursively
    """
    documents = []

    file_types = {
        ".pdf": PyPDFLoader, 
        ".csv": CSVLoader,
        ".docx": Docx2txtLoader,
        ".doc": UnstructuredWordDocumentLoader,
        ".dot": UnstructuredWordDocumentLoader
    }

    if os.path.isfile(source_dir):
        ext = os.path.splitext(source_dir)[1].lower()
        if ext in file_types:
            try:
                loader = file_types[ext](source_dir)
                documents.extend(loader.load())
            except Exception as e:
                print(f"Failed to load {source_dir}: {e}")
    elif os.path.isdir(source_dir):
        for root, dirs, files in os.walk(source_dir):
            for file in files:
                ext = os.path.splitext(file)[1].lower()
                if ext in file_types:
                    file_path = os.path.join(root, file)
                    try:
                        loader = file_types[ext](file_path)
                        documents.extend(loader.load())
                    except Exception as e:
                        print(f"Failed to load {file_path}: {e}")
    return documents
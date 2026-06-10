import os

from pipeline import get_qa_chain, query_system


# doc_directory = "static/docs"


content_dir = os.path.join("static", "docs", "Affidavit - Grant of Probate.pdf")
# content_dir = "Affidavit - Grant of Probate.pdf"

qa_chain = get_qa_chain(source_dir=content_dir)

query = "What is the general overview of the document?"
print(query_system(query, qa_chain))
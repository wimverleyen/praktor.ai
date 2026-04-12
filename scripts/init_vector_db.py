"""
Build (or rebuild) the FAISS vector store from a directory of PDF files.

Usage:
  python scripts/init_vector_db.py --pdf-dir /path/to/pdfs --db-path /path/to/vector_db

The script:
  1. Loads all PDF files found under --pdf-dir (recursively).
  2. Splits them into chunks suitable for embedding.
  3. Embeds each chunk with OllamaEmbeddings.
  4. Saves the resulting FAISS index to --db-path.

Re-running overwrites the existing store, so run only when the source PDFs change.
"""

import argparse
import sys
import os
from pathlib import Path

# Allow running from project root without installing the package
sys.path.insert(0, str(Path(__file__).parent.parent / 'praktor'))

from langchain_community.document_loaders import PyPDFLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.embeddings import OllamaEmbeddings
from langchain_community.vectorstores import FAISS

from settings import MODEL, VECTOR_DB, create_log

log = create_log()


def load_pdfs(pdf_dir: str) -> list:
    pdf_dir = Path(pdf_dir)
    if not pdf_dir.exists():
        raise FileNotFoundError(f"PDF directory not found: {pdf_dir}")

    pdf_files = list(pdf_dir.rglob('*.pdf'))
    if not pdf_files:
        raise ValueError(f"No PDF files found in {pdf_dir}")

    print(f"Found {len(pdf_files)} PDF file(s) in {pdf_dir}")
    log.debug(f"Loading {len(pdf_files)} PDFs from {pdf_dir}")

    documents = []
    for pdf_path in pdf_files:
        print(f"  Loading: {pdf_path.name}")
        loader = PyPDFLoader(str(pdf_path))
        documents.extend(loader.load())

    print(f"Loaded {len(documents)} page(s) total")
    log.debug(f"Loaded {len(documents)} document pages")
    return documents


def build_vector_store(documents: list, db_path: str) -> None:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=150,
    )
    chunks = splitter.split_documents(documents)
    print(f"Split into {len(chunks)} chunk(s)")
    log.debug(f"Split documents into {len(chunks)} chunks")

    print(f"Embedding with model '{MODEL}' — this may take a while...")
    embeddings = OllamaEmbeddings(model=MODEL)

    vector_store = FAISS.from_documents(chunks, embeddings)

    db_path = Path(db_path)
    db_path.mkdir(parents=True, exist_ok=True)
    vector_store.save_local(str(db_path))

    print(f"Vector store saved to: {db_path}")
    log.debug(f"FAISS store saved to {db_path}")


def main():
    parser = argparse.ArgumentParser(
        description='Build the FAISS vector store from PDF documents',
    )
    parser.add_argument(
        '--pdf-dir',
        default=os.getenv('PDF'),
        help='Directory containing PDF files (default: $PDF env var)',
    )
    parser.add_argument(
        '--db-path',
        default=os.getenv('VECTOR_DB'),
        help='Output path for the FAISS index (default: $VECTOR_DB env var)',
    )
    args = parser.parse_args()

    if not args.pdf_dir:
        parser.error('--pdf-dir is required (or set the PDF environment variable)')
    if not args.db_path:
        parser.error('--db-path is required (or set the VECTOR_DB environment variable)')

    documents = load_pdfs(args.pdf_dir)
    build_vector_store(documents, args.db_path)
    print('Done.')


if __name__ == '__main__':
    main()

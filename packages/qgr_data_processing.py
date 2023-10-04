"""
Filename: QGR_data_processing.py
Authors: Marcelo Amaral
Created: Aug 17, 2023
Last Updated: Aug 17, 2023

Description:
This script collects, processes, and organizes personal data into Milvus vector database. 

For detailed descriptions of each function, refer to the function-level docstrings or the script documentation.
"""

#numpy and milvus connection

import os
import json
import torch
import re
import hashlib
import numpy as np
import pandas as pd
import logging
from pymilvus import (
    connections,
    utility,
    FieldSchema, CollectionSchema, DataType,
    Collection,
)
# The powerfull transformers models
from sentence_transformers import SentenceTransformer
#from transformers import AutoTokenizer, AutoModel
#loading files
from langchain.document_loaders import TextLoader
#Text splitter
from langchain.text_splitter import LatexTextSplitter, RecursiveCharacterTextSplitter

#using sentence level embedding
def convertToVector(sentence, model, length):
    # Truncate the sentence to the first 512 characters
    sentence = sentence[:length]

    # Generate the sentence embedding using SBERT
    embedding = model.encode(sentence)

    # Normalize the embeddings
    embedding = embedding / np.linalg.norm(embedding)

    return embedding.tolist()  

def clean_description(description):
    if pd.isnull(description):
        return ''
    # Remove URLs
    description = re.sub(r'http\S+|www.\S+', '', description, flags=re.MULTILINE)
    # Remove timestamps
    description = re.sub(r'\d+:\d+:\d+|\d+:\d+', '', description)
    # Remove sequences of characters that are longer than a certain threshold (e.g., 30)
    description = re.sub(r'\S{30,}', '', description)
    # Remove special characters
    description = re.sub(r'[^a-zA-Z0-9 \n\.]', '', description)
    # Replace multiple consecutive newlines with a single space
    description = re.sub(r'\n+', '\n', description)
    # Remove extra spaces
    description = re.sub(r' +', ' ', description)
    return description

def clean_latex(latex_content):
    cleaned_content = re.sub(r'[\u2022-\u5424]', '', latex_content)
    cleaned_content = re.sub(r'[^\x00-\x7F]+', '', cleaned_content)
    # Remove extra spaces
    cleaned_content = re.sub(r' +', ' ', cleaned_content)
    return cleaned_content



def splitText(content, splitter, length, overlap=20):

    text_splitter = splitter(
        chunk_size = length,
        chunk_overlap  = overlap,
        length_function = len,
    )
    textsDocument = text_splitter.create_documents([content])
    texts = text_splitter.split_documents(textsDocument)
    return texts


def process_file_from_folder(folder_path):
    for root, dirs, files in os.walk(folder_path):
        # Get the relative path from the root folder to the current directory
        rel_path = os.path.relpath(root, folder_path)
        
        # Replace path separators with underscores (or any other character) to create a single string
        category = rel_path.replace(os.path.sep, '_')
        
        # If the relative path is ".", set the category to the base name of the root directory
        if category == ".":
            category = os.path.basename(root)

        for file in files:
            if file.endswith('.json'):
                file_path = os.path.join(root, file)
                with open(file_path, 'r') as json_file:
                    data = json.load(json_file)
                    entry = {
                        "title": data.get("title"),
                        "date": data.get("date"),
                        "authors": ", ".join(data.get("authors", [])),
                        "abstract": data.get("abstract"),
                        "content": data.get("latex_doc"),
                        "category": category
                    }
                return entry, file_path
    return None, None


def generate_document_id(title, authors, date):
    combined_str = f"{title}-{authors}-{date}"
    return hashlib.sha256(combined_str.encode()).hexdigest()



def process_and_insert_documents(entry, sbert_model, collection, partition_name):
    date_value = entry.get("date", "") or "Unknown"  # Use "Unknown" if date is None or empty
    if len(date_value) > 1000:
        date_value = clean_description(date_value)
    date_value = date_value[:250]  # Truncate to 256 characters

    keywords_value = entry.get("keywords", "") or "Unknown"  # Use "Unknown" if keywords is None or empty
    if len(keywords_value) > 1000:
        keywords_value = clean_description(keywords_value)
    keywords_value = keywords_value[:1004]  # Truncate to 1024 characters
    
    author_value = entry.get("authors", "") or "Unknown"
    if len(author_value) > 1000:
        author_value = clean_description(author_value)
    author_value = author_value[:1000]  # Truncate to 1024 characters
    
    title_value = entry.get("title", "") or "Unknown"
    if len(title_value) > 1000:
        title_value = clean_description(title_value)
    title_value = title_value[:900]  # Truncate to 1024 characters
    
    abstract_value = entry.get("abstract", "") or "Unknown"
    if len(abstract_value) > 4000:
        abstract_value = clean_description(abstract_value)
    abstract_value = abstract_value[:4000]  # Truncate to 4096 characters

    category_value = entry.get("category", "") or "Unknown"
    if len(category_value) > 1000:
        category_value = clean_description(category_value)
    category_value = category_value[:250]  # Truncate to 256 characters
    
    content = entry["content"]
    
    if partition_name == "notes":
        content = clean_description(content)
    else:
        content = clean_latex(content)
    docslatex = splitText(content, LatexTextSplitter, 512)

    documentId_value = generate_document_id(title_value, author_value, date_value)

    for chunk in docslatex:
        if len(chunk.page_content) > 512:
            embeddingElement = clean_description(chunk.page_content)
        else:
            embeddingElement = chunk.page_content  # Access the page_content attribute
        content_vector_element = convertToVector(embeddingElement, sbert_model, 512)  # Provide the model and length

        # Create a dictionary for the document
        doc = [
            [documentId_value],
            [title_value],
            [date_value],
            [author_value],
            [abstract_value],
            [keywords_value],
            [category_value],
            [embeddingElement],
            [content_vector_element]
        ]

        # Insert the data
        insert_result = collection.insert(data=doc, partition_name=partition_name)
        if not insert_result:
            title = entry.get("title", "")
            print(f"fail: {title_value} : {embeddingElement}")



# Function to load existing processed files
def load_processed_files(filename):
    try:
        with open(filename, 'r') as json_file:
            return json.load(json_file)
    except FileNotFoundError:
        return []
    

  
def search_documents(query_text, collection_name, sbert_model, partition_name=None, limit=10):
    # Convert the query text to a vector
    query_embedding = convertToVector(query_text, sbert_model, 512)

    # Define search parameters
    search_params = {
        "metric_type": "IP",
        "param": {"nprobe": 1000},
        "round_decimal": -1
    }

    # Load the collection into memory
    collection = Collection(name=collection_name)
    collection.load()

    # Perform the search in the partition or entire collection
    if partition_name:
        results = collection.search(
            [query_embedding],
            "content_vector",
            param=search_params,
            output_fields=["documentId", "title", "date", "authors", "abstract", "keywords", "category", "content"],
            limit=limit,
            partition_names=[partition_name]
        )
    else:
        results = collection.search(
            [query_embedding],
            "content_vector",
            param=search_params,
            output_fields=["documentId", "title", "date", "authors", "abstract", "keywords", "category", "content"],
            limit=limit
        )

    # Sort the results by score in descending order (i.e., most similar first)
    sorted_results = sorted(results[0], key=lambda x: x.score, reverse=True)
    return sorted_results


def group_by_document_id(results):
    grouped_results = {}
    for hit in results:
        document_id = hit.entity.get('documentId')
        if document_id not in grouped_results:
            grouped_results[document_id] = {
                'title': hit.entity.get('title'),
                'date': hit.entity.get('date'),
                'authors': hit.entity.get('authors'),
                'abstract': hit.entity.get('abstract'),
                'keywords': hit.entity.get('keywords'),
                'category': hit.entity.get('category'),
                'contents': [hit.entity.get('content')],
                'score': hit.score
            }
        else:
            grouped_results[document_id]['contents'].append(hit.entity.get('content'))

    return grouped_results


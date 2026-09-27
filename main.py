

from dataclasses import dataclass
import re
import pymupdf4llm
from langchain_experimental.text_splitter import SemanticChunker
from langchain_ollama import OllamaEmbeddings

@dataclass
class Page:
        page_number: int
        text: str
        metadata: dict

@dataclass
class Document:
    metadata: dict
    text: str

subtopics = set()

def extract_abbreviations(text):
    pattern = re.compile(
        r'(?<![A-Za-z])'
        r'([A-Za-z][A-Za-z0-9.\-]*(?:\s+[A-Za-z][A-Za-z0-9.\-]*)?)'
        r'\s*:'
    )

    matches = list(pattern.finditer(text))

    abbreviations = {}
    for match in matches:
        abbreviation = match.group(1).strip()
        definition_start = match.end()
        definition_end = text.find('\n', definition_start)
        if definition_end == -1:
            definition_end = len(text)
        definition = text[definition_start:definition_end].strip()
        abbreviations[abbreviation] = definition

    return abbreviations

def parse_topic(text):

    LEVEL_4_HEADING = re.compile(r"(?m)^#####(?!#)[ \t]+(.+?)[ \t]*#*[ \t]*$")

    headings = []
    for match in LEVEL_4_HEADING.finditer(text):
        heading = match.group(1).strip()
        # Remove optional bold markers, e.g. #### **Heading**
        heading = re.sub(r"^\*\*(.*?)\*\*$", r"\1", heading)
        headings.append(heading)

    topic = [heading for heading in headings if "chapter" not in heading.lower()]
    return topic[0] if topic else None


def extract_subtopics(markdown, topic, chunk_candidates):
    lines = markdown.splitlines()
    i = 1  # Start from the second line to skip the first heading
    if lines and lines[0].strip().startswith("_") and lines[0].strip().endswith("_"):
        while i < len(lines) and not lines[i].startswith("#"):
            i+=1

    prev_chunk_part = lines[1:i]
    print(f"prev_chunk_part: {prev_chunk_part}")

    if chunk_candidates and prev_chunk_part:
        chunk_candidates[-1].text += "\n".join(prev_chunk_part)

    global subtopics

    documents = []
    current_heading = None
    current_content = []

    for line in lines:
        # ##### heading
        match = re.match(r"^######(?!#)\s+(.+?)\s*$", line)

        if match:
            # Save previous subtopic
            if current_heading is not None:
                documents.append(
                    Document(
                        text="\n".join(current_content).strip(),
                        metadata={
                            "topic": topic,
                            "subtopic": current_heading,
                        }
                    )
                )

            # Start new subtopic
            current_heading = match.group(1)
            current_content = []

        elif current_heading is not None:
            current_content.append(line)

    # Save last subtopic
    if current_heading is not None:
        documents.append(
            Document(
                text="\n".join(current_content).strip(),
                metadata={
                    "topic": topic,
                    "subtopic": current_heading,
                }
            )
        )

    

    subtopics.add(current_heading)

    return documents

def split_into_semantic_chunks(documents):
    embeddings = OllamaEmbeddings(model="nomic-embed-text")
    chunker = SemanticChunker(embeddings)
    all_chunks = []

    for doc in documents:
        chunks = chunker.split_text(doc.text)
        for i, chunk in enumerate(chunks):
            all_chunks.append(
                Document(
                    text=chunk,
                    metadata={
                        "topic": doc.metadata["topic"],
                        "subtopic": doc.metadata["subtopic"],
                        "chunk_index": i,
                    }
                )
            )

    return all_chunks

import re
# from langchain_core.documents import Document


MARKDOWN_IMAGE_PATTERN = re.compile(
    r"!\[([^\]]*)\]\(([^)\s]+)(?:\s+[\"']([^\"']*)[\"'])?\)"
)


def attach_images_to_metadata(doc: Document) -> Document:
    """
    Extract Markdown image references from a LangChain Document
    and attach them to the document metadata.

    Supports:
        ![alt text](images/image_01.png)
        ![](images/image_01.png)
        ![alt text](images/image_01.png "caption")

    Adds:
        metadata["images"] = [
            {
                "path": "...",
                "alt": "...",
                "title": "..."
            }
        ]
    """

    images = []

    for match in MARKDOWN_IMAGE_PATTERN.finditer(doc.text):
        alt_text = match.group(1)
        image_path = match.group(2)
        title = match.group(3)

        images.append({
            "path": image_path,
            "alt": alt_text,
            "title": title,
        })

    # Don't mutate the original metadata dictionary
    metadata = dict(doc.metadata)

    if images:
        metadata["images"] = images
    else:
        metadata["images"] = []

    return Document(
        text=doc.text,
        metadata=metadata,
    )

    

# def docling_convert():
#     from pathlib import Path

#     from docling.datamodel.base_models import InputFormat
#     from docling.datamodel.pipeline_options import (
#         HeadingHierarchyOptions,
#         PdfPipelineOptions,
#     )
#     from docling.document_converter import (
#         DocumentConverter,
#         PdfFormatOption,
#     )

#     pipeline_options = PdfPipelineOptions()

#     pipeline_options.generate_parsed_pages = True

#     pipeline_options.heading_hierarchy_options = HeadingHierarchyOptions(
#         enabled=True,
#     )

#     converter = DocumentConverter(
#         format_options={
#             InputFormat.PDF: PdfFormatOption(
#                 pipeline_options=pipeline_options
#             )
#         }
#     )

#     doc = converter.convert(
#         "standard-treatment-guidelines.pdf"
#     ).document

#     return doc

def main():


    pymupdf_docs = pymupdf4llm.to_markdown("standard-treatment-guidelines.pdf", page_chunks = True, write_images = True, image_path = "images")
    # docling_docs = docling_convert()



    print(f"PyMuPDFLoader loaded {len(pymupdf_docs)} documents.")
    # print(f"Docling loaded {len(docling_docs)} documents.")

    # for i, doc in enumerate(docling_docs.parsed_pages):
    #     with open(f"docling_pages/page_{i + 1}.md", "w", encoding="utf-8") as f:
    #         f.write(doc.text)

    normalised_pages = []
    abbreviations = ""

    for i, doc in enumerate(pymupdf_docs):
        
        if i == 9 or i == 10:
            abbreviations += doc["text"] + " "
    
        

        
        page = Page(
            page_number=i + 1,
            text=doc["text"],
            metadata=doc["metadata"]
        )
        normalised_pages.append(page)

        with open(f"pages/page_{i + 1}.md", "w", encoding="utf-8") as f:
            f.write(doc["text"])

    abbreviations_dict = extract_abbreviations(abbreviations)
    chunk_candidates = []


    for page in normalised_pages:
        page.metadata["abbreviations"] = abbreviations_dict
        text_body = page.text

        prev_topic = topic if 'topic' in locals() else None
        topic = parse_topic(text_body)

        if not topic:
            topic = prev_topic

        documents = extract_subtopics(text_body, topic, chunk_candidates)
        chunk_candidates.extend(documents)

    print(f"Extracted {len(chunk_candidates)} chunk candidates.")
    print("chunk candidates: ")
    for candidate in chunk_candidates[:20]:
        print(candidate)

    chunks = split_into_semantic_chunks(chunk_candidates)
    print(f"Extracted {len(chunks)} semantic chunks.")

    document_with_images = [attach_images_to_metadata(chunk) for chunk in chunks]

    print("semantic chunks: ")
    for chunk in document_with_images[:2000]:
        print(chunk)
    



if __name__ == "__main__":

    main()
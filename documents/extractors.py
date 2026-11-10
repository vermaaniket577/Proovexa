"""
Text extraction engine for PDF, DOCX, TXT, and PPTX files.
Preserves page numbers and paragraph boundaries.
"""
import os
import re
import logging
import unicodedata
from pathlib import Path

logger = logging.getLogger(__name__)


def clean_extracted_string(text: str) -> str:
    """Sanitize extracted string: strip null bytes and normalize Unicode (NFC)."""
    if not text:
        return ""
    # Strip null bytes and non-printable control characters except tabs/newlines
    cleaned = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
    # Normalize Unicode (Devanagari, Latin, accents)
    return unicodedata.normalize('NFC', cleaned)


class ExtractionResult:
    """Result of text extraction from a document."""

    def __init__(self, full_text="", page_count=0, text=None):
        self.pages = []  # List of dicts: {page_number, paragraphs: [{text, para_number}]}
        self.full_text = text if text is not None else full_text
        self.word_count = len(self.full_text.split()) if self.full_text else 0
        self.page_count = page_count
        self.errors = []

    def add_page(self, page_number, paragraphs):
        """Add a page with its paragraphs."""
        page_data = {
            'page_number': page_number,
            'paragraphs': []
        }
        for i, text in enumerate(paragraphs, 1):
            cleaned = clean_extracted_string(text).strip()
            if cleaned:
                page_data['paragraphs'].append({
                    'text': cleaned,
                    'para_number': i,
                })
        if page_data['paragraphs']:
            self.pages.append(page_data)

    def finalize(self):
        """Compute final statistics."""
        self.page_count = len(self.pages)
        parts = []
        for page in self.pages:
            for para in page['paragraphs']:
                parts.append(para['text'])
        self.full_text = '\n\n'.join(parts)
        self.word_count = len(self.full_text.split())
        return self

    def validate(self, min_words=20, raise_exception=False):
        """
        Validate that extraction yielded non-empty, usable text.
        Guards against silent extraction failures that cause false 0% similarity scores.
        """
        clean_text = self.full_text.strip()
        tokens = clean_text.split()
        token_count = len(tokens)

        if len(clean_text) == 0 or token_count == 0:
            err_msg = (
                "Extraction Failed: Extracted document text is empty (extracted 0 words). "
                "File may be an empty document, an image-only scan without OCR, or password-protected."
            )
            logger.error(err_msg)
            if err_msg not in self.errors:
                self.errors.append(err_msg)
            if raise_exception:
                raise ValueError(err_msg)
            return False, err_msg

        if token_count < min_words:
            err_msg = (
                f"Extraction Failed: Extracted only {token_count} words (minimum required is {min_words}). "
                "File may be an image scan, protected PDF, or corrupted document."
            )
            logger.warning(err_msg)
            if err_msg not in self.errors:
                self.errors.append(err_msg)
            if raise_exception:
                raise ValueError(err_msg)
            return False, err_msg

        return True, clean_text


class TextExtractor:
    """Base text extractor."""

    def extract(self, file_path):
        raise NotImplementedError


class PDFExtractor(TextExtractor):
    """Extract text from PDF files using PyMuPDF."""

    def extract(self, file_path):
        import fitz  # PyMuPDF

        result = ExtractionResult()
        try:
            doc = fitz.open(file_path)
            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                text = page.get_text("text")
                if text:
                    # Split into paragraphs by double newlines or significant breaks
                    paragraphs = self._split_paragraphs(text)
                    result.add_page(page_num + 1, paragraphs)
            doc.close()
        except Exception as e:
            logger.error(f"PDF extraction error: {e}")
            result.errors.append(f"PDF extraction error: {str(e)}")

        return result.finalize()

    def _split_paragraphs(self, text):
        """Split text into paragraphs."""
        # Split on double newlines or multiple whitespace lines
        paragraphs = re.split(r'\n\s*\n', text)
        # Clean each paragraph
        cleaned = []
        for p in paragraphs:
            p = ' '.join(p.split())  # Normalize whitespace
            if len(p.strip()) > 0:
                cleaned.append(p)
        return cleaned


class DOCXExtractor(TextExtractor):
    """Extract text from DOCX files using python-docx."""

    def extract(self, file_path):
        from docx import Document as DocxDocument

        result = ExtractionResult()
        try:
            doc = DocxDocument(file_path)
            current_paragraphs = []
            current_page = 1

            for para in doc.paragraphs:
                text = para.text.strip()
                if not text:
                    continue

                # Check for page breaks in paragraph's runs
                has_page_break = False
                for run in para.runs:
                    if run._element.xml.find('w:br') != -1 and 'type="page"' in run._element.xml:
                        has_page_break = True
                        break

                if has_page_break and current_paragraphs:
                    result.add_page(current_page, current_paragraphs)
                    current_paragraphs = []
                    current_page += 1

                current_paragraphs.append(text)

            # Add last page
            if current_paragraphs:
                result.add_page(current_page, current_paragraphs)

        except Exception as e:
            logger.error(f"DOCX extraction error: {e}")
            result.errors.append(f"DOCX extraction error: {str(e)}")

        return result.finalize()


class TXTExtractor(TextExtractor):
    """Extract text from plain text files."""

    def extract(self, file_path):
        result = ExtractionResult()
        try:
            encodings = ['utf-8', 'utf-8-sig', 'utf-16', 'utf-16-le', 'latin-1', 'cp1252']
            text = None
            for encoding in encodings:
                try:
                    with open(file_path, 'r', encoding=encoding) as f:
                        text = f.read()
                    break
                except (UnicodeDecodeError, UnicodeError):
                    continue

            if text is None:
                result.errors.append("Could not decode the text file with supported encodings.")
                return result.finalize()

            text = clean_extracted_string(text)
            # Split into paragraphs
            paragraphs = re.split(r'\n\s*\n', text)
            cleaned = [p.strip() for p in paragraphs if p.strip()]

            # Treat every ~50 paragraphs as a "page" for long documents
            page_size = 50
            for i in range(0, len(cleaned), page_size):
                page_paragraphs = cleaned[i:i + page_size]
                result.add_page((i // page_size) + 1, page_paragraphs)

        except Exception as e:
            logger.error(f"TXT extraction error: {e}")
            result.errors.append(f"TXT extraction error: {str(e)}")

        return result.finalize()


class PPTXExtractor(TextExtractor):
    """Extract text from PPTX files using python-pptx."""

    def extract(self, file_path):
        from pptx import Presentation

        result = ExtractionResult()
        try:
            prs = Presentation(file_path)
            for slide_num, slide in enumerate(prs.slides, 1):
                paragraphs = []
                for shape in slide.shapes:
                    if hasattr(shape, "text") and shape.text.strip():
                        paragraphs.append(clean_extracted_string(shape.text.strip()))
                    if shape.has_table:
                        table = shape.table
                        for row in table.rows:
                            row_text = ' | '.join(
                                clean_extracted_string(cell.text.strip()) for cell in row.cells if cell.text.strip()
                            )
                            if row_text:
                                paragraphs.append(row_text)
                if paragraphs:
                    result.add_page(slide_num, paragraphs)

        except Exception as e:
            logger.error(f"PPTX extraction error: {e}")
            result.errors.append(f"PPTX extraction error: {str(e)}")

        return result.finalize()


def get_extractor(file_type):
    """Factory function to get the appropriate extractor."""
    extractors = {
        'pdf': PDFExtractor,
        'docx': DOCXExtractor,
        'txt': TXTExtractor,
        'pptx': PPTXExtractor,
    }
    extractor_class = extractors.get(file_type.lower())
    if extractor_class is None:
        raise ValueError(f"Unsupported file type: {file_type}")
    return extractor_class()


def extract_text(file_path, file_type, min_words: int = 20, validate: bool = True):
    """
    Extract text from a document file and validate the output.

    Args:
        file_path: Path to the file
        file_type: File type (pdf, docx, txt, pptx)
        min_words: Minimum word threshold to prevent false 0% similarity checks
        validate: Whether to run word count and non-empty assertions

    Returns:
        ExtractionResult with pages, paragraphs, and statistics
    """
    extractor = get_extractor(file_type)
    result = extractor.extract(file_path)

    # Assertion logging immediately after extraction
    logger.info(
        "Document text extraction complete for '%s' [%s]: %d words, %d pages, %d chars, %d error(s)",
        file_path, file_type, result.word_count, result.page_count, len(result.full_text), len(result.errors)
    )

    if validate and not result.errors:
        result.validate(min_words=min_words)

    return result


def extract_and_validate_text(file_path, file_type: str = None, min_words: int = 20) -> str:
    """
    Extract, validate, and return the cleaned text of a document.
    Throws a descriptive ValueError if word count is under min_words or extraction is empty.
    Guarantees no empty string is ever passed to the similarity matcher.
    """
    if file_type is None:
        ext = os.path.splitext(file_path)[1].lower().lstrip('.')
        file_type = ext or 'txt'

    result = extract_text(file_path, file_type, min_words=min_words, validate=True)

    if result.errors:
        raise ValueError(f"Extraction Failed: {'; '.join(result.errors)}")

    clean_text = result.full_text.strip()
    word_count = len(clean_text.split())

    if word_count < min_words:
        raise ValueError(
            f"Extraction Failed: Extracted only {word_count} words. "
            "File may be an image scan, protected PDF, or corrupted document."
        )

    return clean_text

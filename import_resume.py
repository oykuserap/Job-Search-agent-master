"""Import your resume (PDF or .txt) as the master resume used for AI scoring and tailoring.

Usage:
    python import_resume.py ~/Downloads/My_Resume.pdf
"""

import shutil
import sys
from pathlib import Path

from config import MASTER_RESUME_PATH


def _pdf_text(path: Path) -> str:
    from pypdf import PdfReader

    pages = [page.extract_text() or "" for page in PdfReader(str(path)).pages]
    lines = [line.rstrip() for page in pages for line in page.splitlines()]
    return "\n".join(lines).strip()


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__.strip())
        return 1

    source = Path(sys.argv[1]).expanduser().resolve()
    if not source.exists():
        print(f"File not found: {source}")
        return 1

    MASTER_RESUME_PATH.parent.mkdir(parents=True, exist_ok=True)
    suffix = source.suffix.lower()
    if suffix == ".pdf":
        text = _pdf_text(source)
        # Keeping the PDF next to the text lets generated resumes reuse its hyperlinks.
        shutil.copyfile(source, MASTER_RESUME_PATH.with_suffix(".pdf"))
    elif suffix in (".txt", ".md"):
        text = source.read_text(encoding="utf-8").strip()
    else:
        print("Unsupported file type. Use a .pdf or .txt (export .docx to PDF first).")
        return 1

    if len(text) < 200:
        print("Very little text was extracted. If the PDF is a scanned image, paste your")
        print(f"resume text into {MASTER_RESUME_PATH} manually instead.")
        return 1

    MASTER_RESUME_PATH.write_text(text + "\n", encoding="utf-8")
    print(f"Saved {len(text.splitlines())} lines to {MASTER_RESUME_PATH}")
    print("Open it and check that the section headings (SUMMARY, EXPERIENCE, SKILLS,")
    print("EDUCATION) are on their own lines, as in resume/master_resume.example.txt.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

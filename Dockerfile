FROM python:3.11-slim

# Wajib untuk Hugging Face Spaces: gunakan user dengan UID 1000
RUN useradd -m -u 1000 user
USER user
ENV PATH="/home/user/.local/bin:$PATH"

WORKDIR /app

# Copy requirements dan install dependencies
COPY --chown=user requirements.txt requirements.txt
RUN pip install --no-cache-dir --upgrade -r requirements.txt

# Copy seluruh file aplikasi
COPY --chown=user . .

# Port default Hugging Face Spaces
ENV PORT=7860
EXPOSE 7860

# Jalankan bot
CMD ["python", "scraper_maujual.py"]

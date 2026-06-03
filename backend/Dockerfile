FROM python:3.12-slim

# 安裝 ffmpeg, rubberband-cli, redis-server 等音訊處理與佇列所需的系統軟體
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    rubberband-cli \
    redis-server \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 先升級 pip 並安裝 CPU 版的 PyTorch，以大幅縮小 Docker Image 體積並加速 Hugging Face 建置速度
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir torch torchaudio --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir -r requirements.txt

# 複製程式碼
COPY . .

# 預先下載 Demucs 人聲分離模型，避免在 Space 啟動後首次分離時下載模型而超時
ENV DEMUCS_DEVICE=cpu
RUN python -c "import demucs.api; demucs.api.Separator(model='htdemucs_ft')"

# 暴露 FastAPI API 的連接埠（Hugging Face 規定容器必須暴露 7860）
EXPOSE 7860

# 賦予啟動腳本執行權限並啟動
RUN chmod +x start-space.sh
CMD ["./start-space.sh"]

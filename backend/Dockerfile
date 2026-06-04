FROM python:3.10-slim

# 設定環境變數
ENV PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive \
    TORCH_HOME=/root/.cache/torch

# 安裝系統依賴：ffmpeg（轉檔）、git（安裝 demucs 用）、rubberband-cli（移調用）與 build-essential
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    git \
    rubberband-cli \
    build-essential \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /code

# 複製依賴清單
COPY ./requirements.txt /code/requirements.txt

# 升級 pip 並安裝 Python 依賴
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 以無依賴模式安裝 demucs，避免破壞已安裝的 torchaudio
RUN pip install --no-cache-dir --no-deps git+https://github.com/facebookresearch/demucs

# 預先下載 demucs 兩套模型權重檔，直接打包至映像檔中，避免冷啟動重複下載
RUN python3 -c "import demucs.api; demucs.api.Separator(model='htdemucs_6s'); demucs.api.Separator(model='htdemucs')"

# 複製後端所有代碼
COPY . .

# 暴露 7860 連接埠
EXPOSE 7860

# 啟動 Gradio 服務
CMD ["python", "app.py"]

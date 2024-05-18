FROM python:3.11-slim
WORKDIR /bot
COPY requirements.txt requirements.txt
RUN pip install -r requirements.txt
COPY bot.py /bot/bot.py
CMD ["python", "bot.py"]

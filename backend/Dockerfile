# Прод-образ бэкенда для облачного хостинга (Koyeb/Render/любой Docker-хостинг).
# Локально по-прежнему используется docker-compose.yml с python:3.13-slim + inline-командой -
# этот файл нужен только когда рядом нет docker-compose, а хостинг умеет собирать один контейнер.
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Платформа сама подставит PORT (Koyeb/Render); 8000 - запасной вариант для локального docker run.
ENV PORT=8000
EXPOSE 8000

CMD ["sh", "-c", "python manage.py migrate --noinput && daphne -b 0.0.0.0 -p ${PORT} --proxy-headers quiz.asgi:application"]

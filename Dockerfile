# Используем официальный образ Python
FROM python:3.12-slim

# Устанавливаем рабочую директорию
WORKDIR /app

# Устанавливаем системные зависимости, необходимые для компиляции
# Включая Rust и Cargo для сборки pydantic-core
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    build-essential \
    curl \
    && curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y \
    && . $HOME/.cargo/env \
    && rm -rf /var/lib/apt/lists/*

# Добавляем Cargo в PATH
ENV PATH="/root/.cargo/bin:${PATH}"

# Копируем файл с зависимостями
COPY requirements.txt .

# Устанавливаем Python-зависимости
# Теперь компиляция пройдёт успешно, так как есть все инструменты
RUN pip install --no-cache-dir -r requirements.txt

# Копируем весь код бота
COPY . .

# Команда для запуска бота
CMD ["python", "bot.py"]

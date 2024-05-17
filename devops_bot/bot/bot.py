import paramiko
import subprocess
import re
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters
from dotenv import load_dotenv
import os
import logging
import psycopg2
from psycopg2 import Error
import time
from telegram import Update
from telegram.ext import CallbackContext


# грузим данные из .env
load_dotenv()

# настраиваем логи
logging.basicConfig(filename='bot.log', level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# словарь для хранения состояний пользователей
user_states = {}

# получаем ssh креды из .env
RM_HOST = os.getenv("RM_HOST")
RM_PORT = int(os.getenv("RM_PORT"))
RM_USER = os.getenv("RM_USER")
RM_PASSWORD = os.getenv("RM_PASSWORD")

# настраиваем ssh соединение и выполнение команд
def ssh_exec_command(command):
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(RM_HOST, port=RM_PORT, username=RM_USER, password=RM_PASSWORD)
    stdin, stdout, stderr = ssh.exec_command(command)
    output = stdout.read().decode('utf-8')
    ssh.close()
    return output

def connect_to_db():
    try:
        conn = psycopg2.connect(
            dbname=os.getenv("DB_DATABASE"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            host=os.getenv("DB_HOST"),
            port=os.getenv("DB_PORT")
        )
        return conn
    except Error as e:
        logger.error(f"Ошибка подключения к PostgreSQL: {e}")
        return None

def check_database_availability():
    max_attempts = 10
    delay_seconds = 5
    for attempt in range(1, max_attempts + 1):
        logger.info(f"Попытка подключения к базе данных: {attempt}/{max_attempts}")
        conn = connect_to_db()
        if conn:
            logger.info("Подключение к базе данных успешно.")
            conn.close()
            return True
        else:
            logger.warning("Не удалось подключиться к базе данных.")
            if attempt < max_attempts:
                logger.info(f"Ожидание {delay_seconds} секунд перед следующей попыткой...")
                time.sleep(delay_seconds)
    logger.error("Превышено максимальное количество попыток подключения к базе данных.")
    return False

def get_emails():
    conn = connect_to_db()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT email FROM emails")
            emails = [row[0] for row in cursor.fetchall()]
            conn.close()
            return emails
        except Error as e:
            logger.error(f"Error fetching emails: {e}")
            conn.close()
            return []
    else:
        return []
def get_phone_numbers():
    conn = connect_to_db()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT phone_number FROM phone_numbers")
            phone_numbers = [row[0] for row in cursor.fetchall()]
            conn.close()
            return phone_numbers
        except Error as e:
            logger.error(f"Error fetching phonenumbers: {e}")
            conn.close()
            return []
    else:
        return []

def get_emails_handler(update, context):
    emails = get_emails()
    if emails:
        update.message.reply_text('Список email-адресов:\n' + '\n'.join(emails))
    else:
        update.message.reply_text('Список email-адресов пуст.')

def get_phone_numbers_handler(update, context):
    phone_numbers = get_phone_numbers()
    if phone_numbers:
        update.message.reply_text('Список номеров телефонов:\n' + '\n'.join(phone_numbers))
    else:
        update.message.reply_text('Список номеров телефонов пуст.')

TOKEN = os.getenv('TOKEN')
LOG_FILE_PATH = "/var/log/postgresql/postgresql.log"

updater = Updater(token=TOKEN, use_context=True)

dispatcher = updater.dispatcher

def get_repl_log(update: Update, context: CallbackContext) -> None:
    try:
        # Выполнение команды для получения логов
        result = subprocess.run(
            ["bash", "-c", f"cat {LOG_FILE_PATH} | grep repl | tail -n 15"],
            capture_output=True,
            text=True,
            check=True  # Проверка наличия ошибок выполнения
        )
        logs = result.stdout
        if logs:
            update.message.reply_text(f"Последние репликационные логи:\n{logs}")
        else:
            update.message.reply_text("Репликационные логи не найдены.")
    except subprocess.CalledProcessError as e:
        update.message.reply_text(f"Ошибка при выполнении команды: {e}")
    except Exception as e:
        update.message.reply_text(f"Ошибка при получении логов: {str(e)}")

        # Создаем обработчик команды /get_repl_logs
repl_logs_handler = CommandHandler('get_repl_log', get_repl_log)


def find_email(update, context):
    user_states[update.message.chat_id] = 'email'
    update.message.reply_text('Пожалуйста, отправьте текст, в котором нужно найти email-адреса.')

def find_phone_number(update, context):
    user_states[update.message.chat_id] = 'phone'
    update.message.reply_text('Пожалуйста, отправьте текст, в котором нужно найти номера телефонов.')

def add_emails_to_db(emails):
    conn = connect_to_db()
    if conn:
        try:
            cursor = conn.cursor()
            for email in emails:
                cursor.execute("INSERT INTO emails (email) VALUES (%s)", (email,))
            conn.commit()
            conn.close()
        except Error as e:
            logger.error(f"Ошибка при добавлении email-адресов в базу данных: {e}")
            conn.rollback()
            conn.close()

def add_phone_numbers_to_db(phone_numbers):
    conn = connect_to_db()
    if conn:
        try:
            cursor = conn.cursor()
            for phone_number in phone_numbers:
                cursor.execute("INSERT INTO phone_numbers (phone_number) VALUES (%s)", (phone_number,))
            conn.commit()
            conn.close()
        except Error as e:
            logger.error(f"Ошибка при добавлении номеров телефонов в базу данных: {e}")
            conn.rollback()
            conn.close()

def yes_handler(update, context):
    chat_id = update.message.chat_id
    if chat_id in user_states:
        if user_states[chat_id] == 'email':
            emails = context.chat_data.get('emails_to_add', [])
            add_emails_to_db(emails)
            update.message.reply_text('Email-адреса успешно добавлены в базу данных.')
        elif user_states[chat_id] == 'phone':
            phone_numbers = context.chat_data.get('phone_numbers_to_add', [])
            add_phone_numbers_to_db(phone_numbers)
            update.message.reply_text('Номера телефонов успешно добавлены в базу данных.')
        del user_states[chat_id]
        context.chat_data.clear()
    else:
        update.message.reply_text('Неверная команда.')

def no_handler(update, context):
    chat_id = update.message.chat_id
    if chat_id in user_states:
        update.message.reply_text('Операция отменена.')
        del user_states[chat_id]
        context.chat_data.clear()
    else:
        update.message.reply_text('Неверная команда.')

# обработка /verify_password
def verify_password(update, context):
    user_states[update.message.chat_id] = 'password'
    update.message.reply_text('Пожалуйста, отправьте пароль для проверки его сложности.')

# требуемый функционал по сбору данных с удаленного хоста
def get_release(update, context):
    output = ssh_exec_command("cat /etc/*release")
    update.message.reply_text(output)

def get_uname(update, context):
    output = ssh_exec_command("uname -a")
    update.message.reply_text(output)

def get_uptime(update, context):
    output = ssh_exec_command("uptime")
    update.message.reply_text(output)

def get_df(update, context):
    output = ssh_exec_command("df -h")
    update.message.reply_text(output)

def get_free(update, context):
    output = ssh_exec_command("free -m")
    update.message.reply_text(output)

def get_mpstat(update, context):
    output = ssh_exec_command("mpstat")
    update.message.reply_text(output)
def get_w(update, context):
    output = ssh_exec_command("w")
    update.message.reply_text(output)

def get_auths(update, context):
    output = ssh_exec_command("last -n 10")
    update.message.reply_text(output)

def get_critical(update, context):
    output = ssh_exec_command("tail -n 5 /var/log/syslog")
    update.message.reply_text(output)

def get_ps(update, context):
    output = ssh_exec_command("ps")
    update.message.reply_text(output)

def get_ss(update, context):
    output = ssh_exec_command("ss -tuln")
    update.message.reply_text(output)

def get_apt_list(update, context):
    args = context.args
    if args:
        package_name = args[0]
        output = ssh_exec_command(f"apt show {package_name}")
    else:
        output = ssh_exec_command("apt list --installed | head -n 10")
    update.message.reply_text(output)

def get_services(update, context):
    output = ssh_exec_command("systemctl list-units --type=service --state=running")
    update.message.reply_text(output)

# обработка текстовых сообщений
def text_message(update, context):
    chat_id = update.message.chat_id
    text = update.message.text
    if chat_id in user_states:
        if user_states[chat_id] == 'email':
            emails = find_emails(text)
            if emails:
                context.chat_data['emails_to_add'] = emails
                update.message.reply_text('Найденные email-адреса:\n' + '\n'.join(emails) + '\nДобавить в базу данных? (/yes или /no)')
            else:
                update.message.reply_text('Email-адреса не найдены.')
        elif user_states[chat_id] == 'phone':
            phone_numbers = find_phone_numbers(text)
            if phone_numbers:
                context.chat_data['phone_numbers_to_add'] = phone_numbers
                update.message.reply_text('Найденные номера телефонов:\n' + '\n'.join(phone_numbers) + '\nДобавить в базу данных? (/yes или /no)')
            else:
                update.message.reply_text('Номера телефонов не найдены.')
    else:
        update.message.reply_text('Неверная команда. Используйте /find_email, /find_phone_number, /verify_password, /get_release, /get_uname, /get_uptime, /get_df, /get_free, /get_mpstat, /get_w, /get_auths, /get_critical, /get_ps, /get_ss, /get_apt_list, /get_services или /get_repl_log /get_phone_numbers, /get_emails') 

 
def find_emails(text):
    pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b'
    emails = set(re.findall(pattern, text))
    return list(emails)

def find_phone_numbers(text):
    pattern = r'((?:\+7|8)[-\s]?[(]?\d{3}[)]?[-\s]?\d{3}[-\s]?\d{2}[-\s]?\d{2})'
    phone_numbers = set(re.findall(pattern, text))
    return list(phone_numbers)

# проверка сложности пароля
def check_password_complexity(password):
    pattern = r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]{8,}$'
    return bool(re.match(pattern, password))

def main():
    if check_database_availability():
        updater = Updater(os.getenv("TOKEN"), use_context=True) 
        dp = updater.dispatcher 
        # добавляем обработчики команд
        dp.add_handler(CommandHandler("find_email", find_email)) 
        dp.add_handler(CommandHandler("find_phone_number", find_phone_number)) 
        dp.add_handler(CommandHandler("verify_password", verify_password))
        dp.add_handler(CommandHandler("get_release", get_release))
        dp.add_handler(CommandHandler("get_uname", get_uname))
        dp.add_handler(CommandHandler("get_uptime", get_uptime))
        dp.add_handler(CommandHandler("get_df", get_df))
        dp.add_handler(CommandHandler("get_free", get_free))
        dp.add_handler(CommandHandler("get_mpstat", get_mpstat))
        dp.add_handler(CommandHandler("get_w", get_w))
        dp.add_handler(CommandHandler("get_auths", get_auths))
        dp.add_handler(CommandHandler("get_critical", get_critical))
        dp.add_handler(CommandHandler("get_ps", get_ps))
        dp.add_handler(CommandHandler("get_ss", get_ss))
        dp.add_handler(CommandHandler("get_apt_list", get_apt_list))
        dp.add_handler(CommandHandler("get_services", get_services))
        dp.add_handler(CommandHandler("get_repl_log", get_repl_log))
        dp.add_handler(CommandHandler("get_emails", get_emails_handler))
        dp.add_handler(CommandHandler("get_phone_numbers", get_phone_numbers_handler))
        dp.add_handler(CommandHandler("yes", yes_handler))
        dp.add_handler(CommandHandler("no", no_handler))
        dp.add_handler(MessageHandler(Filters.text & ~Filters.command, text_message)) 
        updater.start_polling() 
        updater.idle()
    else:
        logger.error("Бот не может быть запущен из-за проблем с подключением к базе данных.")

if __name__ == "__main__":
    main()


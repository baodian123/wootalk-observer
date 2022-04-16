from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from time import sleep
from random import randint
import threading
import win32api

message_stack = []
message_stack_lock = threading.Lock()
monitor = [win32api.GetSystemMetrics(0), win32api.GetSystemMetrics(1)]
monitor_lock = threading.Lock()
screen_start_index = 0
sync = threading.Semaphore(0)
running_state = True
running_state_lock = threading.Lock()
q1 = []
q1_lock = threading.Lock()
q2 = []
q2_lock = threading.Lock()
start_lock = threading.Lock()

class Chat(object):
    def __init__(self, site, port):
        self.port = port
        self.site = site
        self.send_queue = None
        self.receive_queue = None
        self.send_lock = None
        self.receive_lock = None

        q1_lock.acquire()
        if len(q1) == 0:
            self.send_queue = q1
            self.send_lock = q1_lock
            self.receive_queue = q2
            self.receive_lock = q2_lock
        else:
            self.send_queue = q2
            self.send_lock = q2_lock
            self.receive_queue = q1
            self.receive_lock = q1_lock

        self.send_queue.append(self.port)
        q1_lock.release()

    def chrome_options(self):
        options = webdriver.ChromeOptions()
        options.add_argument('--disable-software-rasterizer')
        options.add_argument('--disable-gpu')
        options.add_argument('--disable-extensions')
        options.add_argument('--incognito')
        return options

    def launch_driver(self):
        global screen_start_index
        self.driver = webdriver.Chrome(port=self.port, options=self.chrome_options())
        self.driver.get(self.site)

        monitor_lock.acquire()
        self.driver.set_window_size(monitor[0]/2, monitor[1]/3*2)
        self.driver.set_window_position(screen_start_index, 0)
        screen_start_index += monitor[0]/2
        monitor_lock.release()

    def close_driver(self):
        self.driver.quit()

    def wait_element(self, locate, timeout=10):
        try:
            WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((By.XPATH, locate))
            )
        except:
            raise Exception("locate: {} not found".format(locate))

class WootalkChat(Chat):
    def __init__(self, port):
        Chat.__init__(self, "https://wootalk.today/", port)
        self.launch_driver()
        self.start_chat()

    def start_chat(self):
        self.wait_element("//*[@id='startButton']")
        start_lock.acquire()
        sleep(randint(1, 3))
        self.driver.find_element_by_xpath("//*[@id='startButton']").click()
        start_lock.release()
        self.wait_element("//*[contains(@class, 'system text') and contains(normalize-space(), '加密連線完成，開始聊天囉！')]")

    def listening(self):
        def parse_text(text):
            return text.split('\n')[0][4:]

        def send(text):
            self.driver.find_element_by_xpath("//*[@id='messageInput']").send_keys(text)
            self.driver.find_element_by_xpath("//*[@id='sendButton']//input[@type='button']").click()

            # should add post condition here to ensure message is sent
            # post condition should avoid repeated text
            # not have a good idea currently

        def receive():
            self.receive_lock.acquire()
            if len(self.receive_queue) != 0:
                for text in self.receive_queue:
                    send(text)
                self.receive_queue.clear()
            self.receive_lock.release()

        def get_message(path):
            try:
                element = self.driver.find_element_by_xpath(path)
                self.send_lock.acquire()
                self.send_queue.append(parse_text(element.get_attribute('innerText')))
                self.send_lock.release()
                message_stack_lock.acquire()
                message_stack.append((self.port, parse_text(element.get_attribute('innerText'))))
                message_stack_lock.release()
                return element.get_attribute('mid')
            except NoSuchElementException:
                return None
            except:
                raise Exception("Unknown error occur - Get Message.")

        def user_leave():
            try:
                global running_state
                element = self.driver.find_element_by_xpath("//*[@id='messages' and .//*[contains(normalize-space(), '對方離開了，請按離開按鈕回到首頁')]]")
                running_state_lock.acquire()
                running_state = False
                running_state_lock.release()
                return element
            except NoSuchElementException:
                return None
            except:
                raise Exception("Unknown error occur - User Leave.")

        def quit_chat():
            self.driver.find_element_by_xpath("//*[@id='changeButton']//*[@type='button']").click()
            try:
                self.wait_element("//*[contains(@class, 'mfp-content')]//*[@id='popup-yes']", timeout=3)
                self.driver.find_element_by_xpath("//*[contains(@class, 'mfp-content')]//*[@id='popup-yes']").click()
            finally:
                self.wait_element("//*[@id='startButton']")

        sync.acquire()
        index = None
        while index == None and running_state:
            receive()
            index = get_message("//*[contains(@class, 'stranger text')]")
            user_leave()

        while running_state:
            receive()
            next_index = get_message("//*[@mid='%s']/following-sibling::*[contains(@class, 'stranger text')]" % index)
            if next_index != None:
                index = next_index
            user_leave()
        quit_chat()

def sync_threads():
    while True:
        if len(q1) == 1 and len(q2) == 1:
            q1.clear()
            q2.clear()
            sync.release()
            sync.release()
            break

def run(port):
    chat = WootalkChat(port)
    chat.listening()
    chat.close_driver()

if __name__ == "__main__":
    threads = [threading.Thread(target=run, args=(4444, )), threading.Thread(target=run, args=(9515, ))]
    for thread in threads:
        thread.start()
    sync_threads()

    for thread in threads:
        thread.join()
    print(message_stack)
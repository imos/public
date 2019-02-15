import argparse
import glob
import queue
import re
import subprocess
import threading


class Collector(threading.Thread):
    def __init__(self):
        self.__output = queue.Queue()
        self.is_failure = False
        super(Collector, self).__init__()
        self.start()

    def run(self):
        while True:
            line = self.__output.get()
            if line is None:
                break
            print(line)

    def put(self, line, is_failure):
        self.__output.put(line)
        if is_failure:
            self.is_failure = True


class Executor(threading.Thread):
    def __init__(self, queue, collector):
        self.__queue = queue
        self.__collector = collector
        super(Executor, self).__init__()
        self.start()

    def run(self):
        try:
            while True:
                item = self.__queue.get(block=False)
                p = subprocess.Popen(
                    item["command"], shell=True,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                stdout, stderr = p.communicate()
                line = stdout.strip().rsplit(b"\n", 1)[-1]
                line = re.sub(b"^=*", b"", line)
                line = re.sub(b"=*$", b"", line)
                line = line.strip()
                if re.match(
                        rb"^\d+ deselected in \d+(\.\d+)? seconds$", line):
                    p.returncode = 0
                extra_info = b""
                if p.returncode != 0:
                    extra_info = b"\n"+stdout+stderr
                self.__collector.put("[%s] %s (%s)%s" % (
                    "SUCCESS" if p.returncode == 0 else "FAILED",
                    item["file"], line.decode("utf-8"),
                    extra_info.decode("utf-8")),
                    p.returncode != 0)
        except queue.Empty:
            pass


def main(args):
    tests = queue.Queue()
    for f in glob.glob(args.filter, recursive=True):
        tests.put({
            "file": f,
            "command": args.pytest + " " + f,
        })
    collector = Collector()
    threads = []
    for i in range(args.threads):
        threads.append(Executor(tests, collector))
    for thread in threads:
        thread.join()
    collector.put(None, False)
    collector.join()
    exit(1 if collector.is_failure else 0)


parser = argparse.ArgumentParser()
parser.add_argument("--filter", default="**/test_*.py")
parser.add_argument("--pytest", default="pytest -m 'not slow and not gpu'")
parser.add_argument("--threads", type=int, default=8)
main(parser.parse_args())

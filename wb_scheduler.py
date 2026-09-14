"""wb_scheduler.py —— 后台定时调度器 (Scheduler)

负责常驻后台自动执行：
1. Token 保活 (Keepalive)：定期检查 Token 剩余寿命，不足 2 小时自动调用 Refresh Token。
2. 每日签到 (Daily Checkin)：每日定时为所有国内版账号自动签到领积分。
3. 猫猫旅行与日常结算 (Cat Travel & Welfare)：自动派出猫猫旅行或领取归来奖励。
4. 状态持久化与看板展示：暴露状态、执行记录、支持手动立即触发与开关切换。
"""
import json
import os
import threading
import time
from wb_tasks import do_cat_travel


class Scheduler:
    def __init__(self, pool, interval_seconds=1800):
        self.pool = pool
        self.interval = interval_seconds
        self.enabled = True
        self._stop_event = threading.Event()
        self._thread = None
        self.last_run_time = None
        self.next_run_time = None
        self.logs = []

    def log(self, msg):
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        entry = f"[{ts}] {msg}"
        self.logs.append(entry)
        if len(self.logs) > 60:
            self.logs = self.logs[-60:]

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        self.log("后台定时调度器已启动")

    def stop(self):
        self._stop_event.set()
        self.log("后台定时调度器已暂停")

    def _run_loop(self):
        # 启动后先休眠 10 秒等待主服务就绪，然后执行初次检查
        time.sleep(10)
        while not self._stop_event.is_set():
            if self.enabled:
                try:
                    self._execute_cycle()
                except Exception as exc:
                    self.log(f"调度执行异常: {exc}")
            self.next_run_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() + self.interval))
            self._stop_event.wait(self.interval)

    def trigger_now(self):
        """手动立即触发一次调度检查。"""
        threading.Thread(target=self._execute_cycle, daemon=True).start()
        return {"ok": True, "msg": "已触发后台调度执行"}

    def _execute_cycle(self):
        self.last_run_time = time.strftime("%Y-%m-%d %H:%M:%S")
        self.log("开始执行周期性巡检与保活任务...")
        if not self.pool or not self.pool.accounts:
            self.log("暂无可用的活跃账号，跳过本次巡检")
            return

        refreshed_count = 0
        checkin_count = 0
        travel_count = 0

        for acc in list(self.pool.accounts):
            uid8 = acc.uid[:8] if acc.uid else "?"
            # 1. 检查 Token 剩余寿命 (小于 2 小时自动刷新保活)
            exp = acc.expires_at or 0
            if exp and (exp - time.time()) < 7200:
                self.log(f"账号 [{uid8}] Token 即将到期，执行主动保活刷新...")
                if acc.refresh():
                    refreshed_count += 1
                    self.log(f"✓ 账号 [{uid8}] Token 自动保活刷新成功")
                else:
                    self.log(f"! 账号 [{uid8}] Token 保活刷新失败: {acc.last_error}")

            # 2. 如果是国内版账号，检查每日签到与猫猫旅行
            if acc.realm == "cn":
                if acc.can_checkin():
                    self.log(f"检测到国内版账号 [{uid8}] 今日尚未签到，执行自动签到...")
                    res = acc.checkin()
                    if res.get("ok"):
                        checkin_count += 1
                        self.log(f"✓ 账号 [{uid8}] 自动签到成功: {res.get('msg')}")
                    else:
                        self.log(f"! 账号 [{uid8}] 自动签到未成功: {res.get('error') or res.get('msg')}")
                    time.sleep(1.0)

                # 检查猫猫旅行
                tr = do_cat_travel(acc)
                if tr.get("action") in ("claim", "depart"):
                    travel_count += 1
                    self.log(f"🐱 账号 [{uid8}] 猫猫日常处理: {tr.get('msg')}")
                time.sleep(1.0)

        self.log(f"巡检完成：Token保活 {refreshed_count} 个，每日签到 {checkin_count} 个，猫猫日常 {travel_count} 个")

    def status(self):
        return {
            "enabled": self.enabled,
            "interval_minutes": round(self.interval / 60),
            "last_run_time": self.last_run_time or "尚未运行",
            "next_run_time": self.next_run_time or "待调度",
            "logs": self.logs[-20:],
        }

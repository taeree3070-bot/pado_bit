import pyupbit
import datetime
import time
import tkinter as tk
from tkinter import messagebox, ttk
import pandas as pd
import os
from threading import Thread

# 파일명 설정
ORDERS_FILE = "trading_orders.csv"
HISTORY_FILE = "trading_history.csv"
CASH_FILE = "trading_cash.txt"
CONFIG_FILE = "trading_config.csv"

class VirtualExchange:
    def __init__(self, cash=1000000):
        self.cash = cash
        self.orders = pd.DataFrame(columns=['ticker', 'step', 'price', 'amount', 'time'])
        self.history = pd.DataFrame(columns=['ticker', 'step', 'profit', 'time'])
        self.fee = 0.0005
        self.load_data()

    def save_data(self):
        try:
            self.orders.to_csv(ORDERS_FILE, index=False, encoding='utf-8-sig')
            self.history.to_csv(HISTORY_FILE, index=False, encoding='utf-8-sig')
            with open(CASH_FILE, "w") as f:
                f.write(str(self.cash))
        except PermissionError:
            print("⚠️ 파일이 열려 있어 저장에 실패했습니다.")

    def load_data(self):
        if os.path.exists(ORDERS_FILE):
            self.orders = pd.read_csv(ORDERS_FILE, encoding='utf-8-sig')
        if os.path.exists(HISTORY_FILE):
            self.history = pd.read_csv(HISTORY_FILE, encoding='utf-8-sig')
        if os.path.exists(CASH_FILE):
            try:
                with open(CASH_FILE, "r") as f:
                    self.cash = float(f.read())
            except: pass

    def buy_layer(self, step, ticker, price, krw_amount):
        amount = krw_amount / price
        total_cost = price * amount
        if self.cash >= total_cost:
            self.cash -= (total_cost * (1 + self.fee))
            new_order = {
                'ticker': ticker, 'step': int(step), 'price': price,
                'amount': amount, 'time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            self.orders = pd.concat([self.orders, pd.DataFrame([new_order])], ignore_index=True)
            self.save_data()
            return True
        return False

    def sell_layer(self, step, ticker, price):
        target = self.orders[(self.orders['ticker'] == ticker) & (self.orders['step'] == int(step))]
        if not target.empty:
            order = target.iloc[0]
            buy_val = order['price'] * order['amount']
            sell_val = price * order['amount']
            profit = (sell_val * (1 - self.fee)) - (buy_val * (1 + self.fee))
            self.cash += (sell_val * (1 - self.fee))
            new_history = {
                'ticker': ticker, 'step': int(step), 'profit': profit,
                'time': datetime.datetime.now().strftime('%m/%d %H:%M:%S')
            }
            self.history = pd.concat([pd.DataFrame([new_history]), self.history], ignore_index=True)
            self.orders = self.orders.drop(target.index)
            self.save_data()
            return profit
        return None

class TickerTab(tk.Frame):
    def __init__(self, parent, ticker, exchange, target_rate, drop_rate, max_step, log_func):
        super().__init__(parent)
        self.ticker = ticker
        self.exchange = exchange
        self.target_rate = target_rate
        self.drop_rate = drop_rate
        self.max_step = max_step
        self.log = log_func # 로그 출력 함수 연결
        self.running = False
        self.last_order_time = 0 
        self.setup_ui()

    def setup_ui(self):
        ctrl_frame = tk.Frame(self)
        ctrl_frame.pack(fill="x", pady=5)

        self.lbl_summary = tk.Label(ctrl_frame, text=f"[{self.ticker}] 익절 {self.target_rate*100:.2f}% / 추매 {self.drop_rate*100:.2f}% / 제한: {self.max_step}차", fg="blue", font=('Arial', 9, 'bold'))
        self.lbl_summary.pack(side="left", padx=10)

        self.btn_toggle = tk.Button(ctrl_frame, text="▶ 매매 시작", command=self.toggle_trading, bg="#27ae60", fg="white", width=15)
        self.btn_toggle.pack(side="right", padx=10)

        main_area = tk.Frame(self)
        main_area.pack(fill="both", expand=True)

        left_frame = tk.Frame(main_area)
        left_frame.grid(row=0, column=0, padx=5, pady=5, sticky="nsew")
        self.info_scroll = tk.Scrollbar(left_frame)
        self.info_scroll.pack(side="right", fill="y")
        self.info_text = tk.Text(left_frame, height=12, width=45, font=('Consolas', 9), yscrollcommand=self.info_scroll.set)
        self.info_text.pack(side="left", fill="both", expand=True)
        self.info_scroll.config(command=self.info_text.yview)

        right_container = tk.Frame(main_area)
        right_container.grid(row=0, column=1, padx=5, pady=5, sticky="nsew")
        self.profit_label = tk.Label(right_container, text="누적 수익: 0원", font=('Arial', 11, 'bold'), fg="#c0392b")
        self.profit_label.pack(pady=5)
        right_scroll_frame = tk.Frame(right_container)
        right_scroll_frame.pack(fill="both", expand=True)
        self.hist_scroll = tk.Scrollbar(right_scroll_frame)
        self.hist_scroll.pack(side="right", fill="y")
        self.history_text = tk.Text(right_scroll_frame, height=10, width=35, bg="#fdfdfd", font=('Consolas', 8), yscrollcommand=self.hist_scroll.set)
        self.history_text.pack(side="left", fill="both", expand=True)
        self.hist_scroll.config(command=self.history_text.yview)

    def toggle_trading(self):
        if not self.running:
            self.running = True
            self.btn_toggle.config(text="■ 매매 중지", bg="#c0392b")
            self.log(f"[{self.ticker}] 매매 시스템을 가동합니다.")
            Thread(target=self.trade_loop, daemon=True).start()
        else:
            self.running = False
            self.btn_toggle.config(text="▶ 매매 시작", bg="#27ae60")
            self.log(f"[{self.ticker}] 매매 시스템을 중지합니다.")

    def trade_loop(self):
        while self.running:
            try:
                curr_price = pyupbit.get_current_price(self.ticker)
                if curr_price is None: continue
                
                current_time = time.time()
                can_order = (current_time - self.last_order_time) >= 3.0
                t_orders = self.exchange.orders[self.exchange.orders['ticker'] == self.ticker].sort_values(by='step', ascending=False)
                
                # 1. 매도(익절) 로직
                if can_order:
                    for _, row in t_orders.iterrows():
                        target_p = row['price'] * (1 + self.target_rate)
                        if curr_price >= target_p:
                            self.log(f"[{self.ticker}] {int(row['step'])}차 익절 조건 감지 (목표:{target_p:,.0f} / 현재:{curr_price:,.0f})")
                            profit = self.exchange.sell_layer(row['step'], self.ticker, curr_price)
                            self.log(f"▶ [{self.ticker}] {int(row['step'])}차 매도 처리되었습니다. (수익: {profit:,.0f}원)")
                            self.last_order_time = time.time()
                            can_order = False
                            break

                # 2. 매수 로직
                if can_order:
                    if t_orders.empty:
                        self.log(f"[{self.ticker}] 신규 1차 진입 시도 ({curr_price:,.0f}원)")
                        if self.exchange.buy_layer(1, self.ticker, curr_price, 6000):
                            self.log(f"▶ [{self.ticker}] 1차 매수 처리되었습니다.")
                            self.last_order_time = time.time()
                    else:
                        latest_step = int(t_orders['step'].max())
                        if latest_step < int(self.max_step):
                            buy_p = t_orders[t_orders['step'] == latest_step]['price'].values[0]
                            drop_p = buy_p * (1 + self.drop_rate)
                            if curr_price <= drop_p:
                                self.log(f"[{self.ticker}] {latest_step+1}차 추매 조건 감지 (기준:{drop_p:,.0f} / 현재:{curr_price:,.0f})")
                                if self.exchange.buy_layer(latest_step + 1, self.ticker, curr_price, 6000):
                                    self.log(f"▶ [{self.ticker}] {latest_step+1}차 매수 처리되었습니다.")
                                    self.last_order_time = time.time()

                self.update_ui(curr_price)
            except Exception as e:
                print(f"[{self.ticker}] Error: {e}")
            time.sleep(1)

    def update_ui(self, price=None):
        t_orders = self.exchange.orders[self.exchange.orders['ticker'] == self.ticker].sort_values(by='step')
        t_history = self.exchange.history[self.exchange.history['ticker'] == self.ticker]
        
        info_scroll_pos = self.info_text.yview()
        self.info_text.delete('1.0', tk.END)
        price_display = f"{price:,.2f}" if price else "대기중"
        status = f"● 현재가: {price_display}\n● 잔고: {self.exchange.cash:,.0f}원\n"
        wait_time = max(0, 3.0 - (time.time() - self.last_order_time))
        if wait_time > 0 and self.running:
            status += f"⏳ 주문 딜레이 대기: {wait_time:.1f}초\n"
        status += "-------------------------------------------\n"
        for _, row in t_orders.iterrows():
            rate_display = f"{((price / row['price']) - 1) * 100:>+7.2f}%" if price else "-------"
            status += f" [{int(row['step']):2}차] | {row['price']:>12,.1f} | {rate_display}\n"
        self.info_text.insert(tk.END, status)
        self.info_text.yview_moveto(info_scroll_pos[0])

        self.profit_label.config(text=f"누적 수익: {t_history['profit'].sum():,.0f}원")
        self.history_text.delete('1.0', tk.END)
        for _, h in t_history.iterrows():
            self.history_text.insert(tk.END, f"[{h['time']}] {int(h['step'])}차: +{h['profit']:,.0f}\n")

class MainApp:
    def __init__(self, root):
        self.root = root
        self.root.title("무한 매매 시뮬레이터 v8.5 (통합 로그 시스템)")
        self.exchange = VirtualExchange()
        self.tabs = {}

        # --- 상단 설정 영역 ---
        config_frame = tk.LabelFrame(root, text="전략 설정 및 종목 추가")
        config_frame.pack(padx=10, pady=5, fill="x")
        
        tk.Label(config_frame, text="종목:").grid(row=0, column=0, padx=5)
        self.ent_ticker = tk.Entry(config_frame, width=10)
        self.ent_ticker.insert(0, "KRW-BTC")
        self.ent_ticker.grid(row=0, column=1, padx=5)
        tk.Button(config_frame, text="종목 추가", command=self.add_ticker_tab, bg="#3498db", fg="white").grid(row=0, column=2, padx=5)
        tk.Label(config_frame, text="익절(%):").grid(row=0, column=3, padx=5); self.ent_target = tk.Entry(config_frame, width=5)
        self.ent_target.grid(row=0, column=4, padx=2)
        tk.Label(config_frame, text="추매(%):").grid(row=0, column=5, padx=5); self.ent_drop = tk.Entry(config_frame, width=5)
        self.ent_drop.grid(row=0, column=6, padx=2)
        tk.Label(config_frame, text="제한차수:").grid(row=0, column=7, padx=5); self.ent_max_step = tk.Entry(config_frame, width=5)
        self.ent_max_step.grid(row=0, column=8, padx=2)
        tk.Button(config_frame, text="현재탭 수정", command=self.update_tab_settings, bg="#f39c12", fg="white").grid(row=0, column=9, padx=10)

        # --- 중간 탭 영역 ---
        self.notebook = ttk.Notebook(root)
        self.notebook.pack(padx=10, pady=5, fill="both", expand=True)
        self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_changed)

        # --- 하단 로그 영역 ---
        log_frame = tk.LabelFrame(root, text="실시간 통합 로그")
        log_frame.pack(padx=10, pady=5, fill="x")
        
        self.log_scroll = tk.Scrollbar(log_frame)
        self.log_scroll.pack(side="right", fill="y")
        self.log_text = tk.Text(log_frame, height=8, bg="#2c3e50", fg="#ecf0f1", font=('Consolas', 9), yscrollcommand=self.log_scroll.set)
        self.log_text.pack(side="left", fill="both", expand=True)
        self.log_scroll.config(command=self.log_text.yview)

        self.load_initial_tabs()
        self.add_log("시스템이 시작되었습니다. 시뮬레이션 데이터 로딩 완료.")

    def add_log(self, message):
        """로그 창에 메시지 추가"""
        timestamp = datetime.datetime.now().strftime("[%H:%M:%S] ")
        self.log_text.insert(tk.END, timestamp + message + "\n")
        self.log_text.see(tk.END) # 항상 최신 로그로 스크롤

    def on_tab_changed(self, event):
        current_id = self.notebook.select()
        if not current_id: return
        tab_obj = self.root.nametowidget(current_id)
        self.ent_ticker.delete(0, tk.END); self.ent_ticker.insert(0, tab_obj.ticker)
        self.ent_target.delete(0, tk.END); self.ent_target.insert(0, f"{tab_obj.target_rate * 100:.2f}")
        self.ent_drop.delete(0, tk.END); self.ent_drop.insert(0, f"{tab_obj.drop_rate * 100:.2f}")
        self.ent_max_step.delete(0, tk.END); self.ent_max_step.insert(0, str(tab_obj.max_step))

    def add_ticker_tab(self):
        ticker = self.ent_ticker.get().upper().strip()
        if ticker in self.tabs: return
        try:
            target, drop, max_step = float(self.ent_target.get())/100, float(self.ent_drop.get())/100, int(self.ent_max_step.get())
        except: target, drop, max_step = 0.005, -0.01, 30
        tab = TickerTab(self.notebook, ticker, self.exchange, target, drop, max_step, self.add_log)
        self.notebook.add(tab, text=ticker)
        self.tabs[ticker] = tab
        self.save_config()
        tab.update_ui()
        self.add_log(f"신규 종목 [{ticker}] 탭이 생성되었습니다.")

    def update_tab_settings(self):
        current_id = self.notebook.select()
        if not current_id: return
        tab_obj = self.root.nametowidget(current_id)
        try:
            tab_obj.target_rate, tab_obj.drop_rate, tab_obj.max_step = float(self.ent_target.get())/100, float(self.ent_drop.get())/100, int(self.ent_max_step.get())
            tab_obj.lbl_summary.config(text=f"[{tab_obj.ticker}] 익절 {tab_obj.target_rate*100:.2f}% / 추매 {tab_obj.drop_rate*100:.2f}% / 제한: {tab_obj.max_step}차")
            self.save_config()
            self.add_log(f"[{tab_obj.ticker}] 전략 수정 완료 (익절:{self.ent_target.get()}%, 추매:{self.ent_drop.get()}%)")
        except: pass

    def save_config(self):
        config_data = [{'ticker': t, 'target_rate': tab.target_rate, 'drop_rate': tab.drop_rate, 'max_step': tab.max_step} for t, tab in self.tabs.items()]
        pd.DataFrame(config_data).to_csv(CONFIG_FILE, index=False)

    def load_initial_tabs(self):
        if os.path.exists(CONFIG_FILE):
            try:
                df = pd.read_csv(CONFIG_FILE)
                for _, row in df.iterrows():
                    ms = row['max_step'] if 'max_step' in df.columns else 30
                    tab = TickerTab(self.notebook, row['ticker'], self.exchange, row['target_rate'], row['drop_rate'], ms, self.add_log)
                    self.notebook.add(tab, text=row['ticker'])
                    self.tabs[row['ticker']] = tab
            except: pass

if __name__ == "__main__":
    root = tk.Tk(); root.geometry("1000x850") # 로그 영역 확보를 위해 세로 크기 증가
    app = MainApp(root); root.mainloop()
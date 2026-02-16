#!/usr/bin/env python3
"""
build_data.py - 日本株データダッシュボード用データ生成スクリプト

data/ と financedata/ のCSVファイルを読み込み、
ダッシュボード用の統合JSONファイル (stock_data.json) を生成する。
"""

import csv
import json
import os
import glob
from collections import OrderedDict

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
FINANCE_DIR = os.path.join(BASE_DIR, 'financedata')
OUTPUT_FILE = os.path.join(BASE_DIR, 'stock_data.json')


def read_csv(filepath):
    rows = []
    with open(filepath, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


def to_float(val):
    if val is None:
        return None
    val = str(val).strip()
    if val == '':
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def to_int(val):
    if val is None:
        return None
    val = str(val).strip()
    if val == '':
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


def get_quarterly_prices(price_rows):
    """日次株価データから四半期末（3月末区切り）の終値を抽出する。"""
    monthly = OrderedDict()
    for row in price_rows:
        date_str = row.get('Date', '').strip()
        close = to_float(row.get('Close'))
        if not date_str or close is None:
            continue
        ym = date_str[:7]
        monthly[ym] = close
    return list(monthly.items())


def find_price_on_date(price_by_date, sorted_dates, target_date):
    """指定日付またはその直前の取引日の終値を取得する。"""
    if target_date in price_by_date:
        return price_by_date[target_date]
    for d in reversed(sorted_dates):
        if d <= target_date:
            return price_by_date[d]
    return None


def process_stock(code, finance_path, price_path):
    """1銘柄のデータを処理し、統合データを返す。"""
    try:
        finance_rows = read_csv(finance_path)
        price_rows = read_csv(price_path)
    except Exception as e:
        print(f"  Error reading {code}: {e}")
        return None

    if not finance_rows or not price_rows:
        return None

    # 株価の日付→終値マッピングを構築
    price_by_date = {}
    for row in price_rows:
        date_str = row.get('Date', '').strip()
        close = to_float(row.get('Close'))
        if date_str and close is not None:
            price_by_date[date_str] = close

    sorted_dates = sorted(price_by_date.keys())
    if not sorted_dates:
        return None

    # 最新の株価
    latest_price = price_by_date[sorted_dates[-1]]

    # 各指標を最新の有効な値から独立して取得
    profit = None
    eps = None
    bps = None
    cf_operating = None

    for row in reversed(finance_rows):
        if profit is None:
            v = to_int(row.get('Profit'))
            if v is not None:
                profit = v
        if eps is None:
            v = to_float(row.get('EarningsPerShare'))
            if v is not None and v != 0:
                eps = v
        if bps is None:
            v = to_float(row.get('BookValuePerShare'))
            if v is not None and v != 0:
                bps = v
        if cf_operating is None:
            v = to_int(row.get('CashFlowOperating'))
            if v is not None and v != 0:
                cf_operating = v
        if all(x is not None for x in [profit, eps, bps, cf_operating]):
            break

    # 指標を計算
    per = None
    if eps and eps != 0:
        per = round(latest_price / eps, 2)

    pbr = None
    if bps and bps != 0:
        pbr = round(latest_price / bps, 2)

    roe = None
    if eps is not None and bps and bps != 0:
        roe = round(eps / bps * 100, 2)

    pcfr = None
    if cf_operating and cf_operating != 0 and eps and eps != 0 and profit and profit != 0:
        shares = abs(profit / eps)
        if shares > 0:
            cfps = cf_operating / shares
            if cfps != 0:
                pcfr = round(latest_price / cfps, 2)

    # --- 過去データの構築 ---

    # 財務データの履歴（各開示日ごと）
    finance_history = []
    for row in finance_rows:
        date = row.get('DisclosedDate', '').strip()
        if not date:
            continue

        entry_profit = to_int(row.get('Profit'))
        entry_eps = to_float(row.get('EarningsPerShare'))
        entry_bps = to_float(row.get('BookValuePerShare'))
        entry_cf = to_int(row.get('CashFlowOperating'))

        # その日の株価を取得
        price_at = find_price_on_date(price_by_date, sorted_dates, date)

        # 各指標を計算
        entry_per = None
        if price_at and entry_eps and entry_eps != 0:
            entry_per = round(price_at / entry_eps, 2)

        entry_pbr = None
        if price_at and entry_bps and entry_bps != 0:
            entry_pbr = round(price_at / entry_bps, 2)

        entry_roe = None
        if entry_eps is not None and entry_bps and entry_bps != 0:
            entry_roe = round(entry_eps / entry_bps * 100, 2)

        entry_pcfr = None
        if (price_at and entry_cf and entry_cf != 0
                and entry_eps and entry_eps != 0
                and entry_profit and entry_profit != 0):
            entry_shares = abs(entry_profit / entry_eps)
            if entry_shares > 0:
                entry_cfps = entry_cf / entry_shares
                if entry_cfps != 0:
                    entry_pcfr = round(price_at / entry_cfps, 2)

        # [date, profit, per, pbr, roe, pcfr]
        finance_history.append([
            date,
            entry_profit,
            entry_per,
            entry_pbr,
            entry_roe,
            entry_pcfr
        ])

    # 月次株価データ（チャート用）
    monthly_prices = get_quarterly_prices(price_rows)

    return {
        'code': code,
        'price': latest_price,
        'profit': profit,
        'per': per,
        'pbr': pbr,
        'roe': roe,
        'pcfr': pcfr,
        'ph': monthly_prices,      # [[date, close], ...]
        'fh': finance_history       # [[date, profit, per, pbr, roe, pcfr], ...]
    }


def main():
    print("日本株データを処理中...")

    # financedata内の全CSVファイルを取得
    finance_files = sorted(glob.glob(os.path.join(FINANCE_DIR, '*.csv')))
    print(f"  financedata: {len(finance_files)} ファイル")

    stocks = []
    skipped = 0

    for fpath in finance_files:
        code = os.path.splitext(os.path.basename(fpath))[0]
        price_path = os.path.join(DATA_DIR, f'{code}.csv')

        if not os.path.exists(price_path):
            skipped += 1
            continue

        result = process_stock(code, fpath, price_path)
        if result:
            stocks.append(result)

    print(f"  処理完了: {len(stocks)} 銘柄 (スキップ: {skipped})")

    # JSONを出力
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(stocks, f, ensure_ascii=False, separators=(',', ':'))

    file_size = os.path.getsize(OUTPUT_FILE) / (1024 * 1024)
    print(f"  出力: {OUTPUT_FILE} ({file_size:.1f} MB)")


if __name__ == '__main__':
    main()

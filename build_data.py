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
CHARTLIST_FILES = [
    os.path.join(BASE_DIR, 'allchart.csv'),
    os.path.join(BASE_DIR, 'allchartlist.csv'),
]

# financedataの全数値フィールド
FINANCE_NUM_FIELDS = [
    'Sales', 'OP', 'OdP', 'NP', 'EPS', 'DEPS',
    'TA', 'Eq', 'EqAR', 'BPS',
    'CFO', 'CFI', 'CFF', 'CashEq',
    'DivAnn', 'FDivAnn', 'FPayoutRatioAnn',
    'FSales', 'FOP', 'FOdP', 'FNP', 'FEPS',
    'NxFSales', 'NxFOP', 'NxFOdP', 'NxFNp', 'NxFEPS',
]

# financedataの文字列フィールド
FINANCE_STR_FIELDS = ['CurFYEn', 'DiscDate', 'NxtFYEn']


def load_chartlist():
    """allchart.csv（互換で allchartlist.csv）からコード→銘柄名のマッピングを読み込む。"""
    mapping = {}
    filepath = next((f for f in CHARTLIST_FILES if os.path.exists(f)), None)
    if not filepath:
        print(f"  警告: {', '.join(CHARTLIST_FILES)} が見つかりません")
        return mapping
    with open(filepath, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        for row in reader:
            if len(row) >= 2:
                code = row[0].strip()
                name = row[1].strip()
                if code:
                    mapping[code] = name
    return mapping


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


def process_stock(code, finance_path, price_path, name):
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

    # 最新の財務データから全フィールドを取得
    latest_finance = {}
    # 文字列フィールド
    for field in FINANCE_STR_FIELDS:
        for row in reversed(finance_rows):
            v = row.get(field, '').strip()
            if v:
                latest_finance[field] = v
                break
        if field not in latest_finance:
            latest_finance[field] = None

    # 数値フィールド（各フィールドを独立に最新の有効値から取得）
    for field in FINANCE_NUM_FIELDS:
        for row in reversed(finance_rows):
            v = to_float(row.get(field))
            if v is not None:
                latest_finance[field] = v
                break
        if field not in latest_finance:
            latest_finance[field] = None

    # 指標を計算
    eps = latest_finance.get('EPS')
    bps = latest_finance.get('BPS')
    np_val = latest_finance.get('NP')
    cfo = latest_finance.get('CFO')

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
    if cfo and cfo != 0 and eps and eps != 0 and np_val and np_val != 0:
        shares = abs(np_val / eps)
        if shares > 0:
            cfps = cfo / shares
            if cfps != 0:
                pcfr = round(latest_price / cfps, 2)

    # 配当利回り
    div_yield = None
    div_ann = latest_finance.get('DivAnn')
    if div_ann and latest_price and latest_price != 0:
        div_yield = round(div_ann / latest_price * 100, 2)

    # 予想配当利回り
    fdiv_yield = None
    fdiv_ann = latest_finance.get('FDivAnn')
    if fdiv_ann and latest_price and latest_price != 0:
        fdiv_yield = round(fdiv_ann / latest_price * 100, 2)

    # ROA
    roa = None
    ta = latest_finance.get('TA')
    if np_val is not None and ta and ta != 0:
        roa = round(np_val / ta * 100, 2)

    # 時価総額
    market_cap = None
    if eps and eps != 0 and np_val is not None:
        shares = abs(np_val / eps)
        if shares > 0:
            market_cap = round(latest_price * shares)

    # 予想PER (Forward PER)
    fper = None
    feps = latest_finance.get('FEPS')
    if feps and feps != 0:
        fper = round(latest_price / feps, 2)

    # PSR (株価売上高倍率)
    sales = latest_finance.get('Sales')
    psr = None
    if market_cap and sales and sales != 0:
        psr = round(market_cap / sales, 2)

    # EV/EBITDA
    cash_eq = latest_finance.get('CashEq')
    op_val = latest_finance.get('OP')
    ev_ebitda = None
    if market_cap and op_val and op_val != 0:
        ev = market_cap - (cash_eq or 0)
        if ev > 0:
            ev_ebitda = round(ev / op_val, 2)

    # --- 過去データの構築 ---

    # 財務データの履歴（各開示日ごと）
    finance_history = []
    for row in finance_rows:
        date = row.get('DiscDate', '').strip()
        if not date:
            continue

        entry_np = to_float(row.get('NP'))
        entry_eps = to_float(row.get('EPS'))
        entry_bps = to_float(row.get('BPS'))
        entry_cfo = to_float(row.get('CFO'))

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
        if (price_at and entry_cfo and entry_cfo != 0
                and entry_eps and entry_eps != 0
                and entry_np and entry_np != 0):
            entry_shares = abs(entry_np / entry_eps)
            if entry_shares > 0:
                entry_cfps = entry_cfo / entry_shares
                if entry_cfps != 0:
                    entry_pcfr = round(price_at / entry_cfps, 2)

        entry_sales = to_float(row.get('Sales'))
        entry_op = to_float(row.get('OP'))
        entry_odp = to_float(row.get('OdP'))
        entry_cashEq = to_float(row.get('CashEq'))

        # 履歴用の時価総額
        entry_market_cap = None
        if price_at and entry_eps and entry_eps != 0 and entry_np and entry_np != 0:
            entry_shares = abs(entry_np / entry_eps)
            if entry_shares > 0:
                entry_market_cap = round(price_at * entry_shares)

        # [date, NP, per, pbr, roe, pcfr, Sales, OP, OdP, EPS, BPS, CFO, CashEq, MarketCap]
        finance_history.append([
            date,
            entry_np,
            entry_per,
            entry_pbr,
            entry_roe,
            entry_pcfr,
            entry_sales,
            entry_op,
            entry_odp,
            entry_eps,
            entry_bps,
            entry_cfo,
            entry_cashEq,
            entry_market_cap,
        ])

    # 月次株価データ（チャート用）
    monthly_prices = get_quarterly_prices(price_rows)

    result = {
        'code': code,
        'name': name,
        'price': latest_price,
    }

    # 文字列フィールド
    for field in FINANCE_STR_FIELDS:
        result[field] = latest_finance.get(field)

    # 数値フィールド
    for field in FINANCE_NUM_FIELDS:
        result[field] = latest_finance.get(field)

    # 計算指標
    result['per'] = per
    result['pbr'] = pbr
    result['roe'] = roe
    result['pcfr'] = pcfr
    result['DivYield'] = div_yield
    result['FDivYield'] = fdiv_yield
    result['roa'] = roa
    result['MarketCap'] = market_cap
    result['fper'] = fper
    result['psr'] = psr
    result['ev_ebitda'] = ev_ebitda

    # 履歴データ
    result['ph'] = monthly_prices       # [[date, close], ...]
    result['fh'] = finance_history      # [[date, profit, per, pbr, roe, pcfr], ...]

    return result


def main():
    print("日本株データを処理中...")

    # 銘柄名マッピングを読み込み
    chartlist = load_chartlist()
    print(f"  銘柄名マッピング: {len(chartlist)} 件")

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

        name = chartlist.get(code, code)
        result = process_stock(code, fpath, price_path, name)
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

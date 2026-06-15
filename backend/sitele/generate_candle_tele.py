"""KOSPI/KOSDAQ 캔들차트 생성기 - MA + Volume"""
import requests
import xml.etree.ElementTree as ET
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import numpy as np
from datetime import datetime
import os
import sys

# 한글 폰트: 서버 리눅스에는 'Noto Sans KR' 가 설치돼 있지 않아 차트 한글이 깨진다.
# 저장소에 동봉된 한화 고딕 ttf(sitele/fonts)를 직접 등록해 OS 무관하게 한글을 렌더한다.
from matplotlib import font_manager as _fm

_FONT_DIR = os.path.join(os.path.dirname(__file__), 'fonts')
_FONT_FAMILY = 'sans-serif'
try:
    for _fn in ('05HanwhaGothicR.ttf', '04HanwhaGothicB.ttf', '06HanwhaGothicL.ttf'):
        _fp = os.path.join(_FONT_DIR, _fn)
        if os.path.exists(_fp):
            _fm.fontManager.addfont(_fp)
    _reg = os.path.join(_FONT_DIR, '05HanwhaGothicR.ttf')
    if os.path.exists(_reg):
        _FONT_FAMILY = _fm.FontProperties(fname=_reg).get_name()
except Exception:
    _FONT_FAMILY = 'Noto Sans KR'  # 폰트 등록 실패 시 기존 동작으로 폴백
plt.rcParams['font.family'] = _FONT_FAMILY
plt.rcParams['axes.unicode_minus'] = False


def fetch_ohlcv(symbol, count=80):
    url = 'https://fchart.stock.naver.com/sise.nhn'
    params = {'symbol': symbol, 'timeframe': 'day', 'count': count, 'requestType': 0}
    r = requests.get(url, params=params)
    root = ET.fromstring(r.text)
    rows = []
    for item in root.iter('item'):
        data = item.attrib['data'].split('|')
        rows.append({
            'Date': pd.to_datetime(data[0]),
            'Open': float(data[1]),
            'High': float(data[2]),
            'Low': float(data[3]),
            'Close': float(data[4]),
            'Volume': int(data[5])
        })
    df = pd.DataFrame(rows)
    df.set_index('Date', inplace=True)
    return df


def draw_single_candle(df_full, out_path, color_up='#ef4444', color_down='#3b82f6'):
    # MA 계산 (전체 데이터로)
    df_full['MA5'] = df_full['Close'].rolling(5).mean()
    df_full['MA20'] = df_full['Close'].rolling(20).mean()
    df_full['MA60'] = df_full['Close'].rolling(60).mean()

    # 최근 40일만 표시
    df = df_full.iloc[-40:].copy()

    # 2행 서브플롯: 캔들(80%) + 거래량(20%)
    fig, (ax, ax_vol) = plt.subplots(2, 1, figsize=(5.8, 5.8), dpi=150,
                                      gridspec_kw={'height_ratios': [4, 1], 'hspace': 0.05})
    fig.patch.set_facecolor('#ffffff')
    fig.subplots_adjust(left=0.12, right=0.95, top=0.95, bottom=0.08)

    width_body = 0.55
    width_wick = 0.12

    for i, (idx, row) in enumerate(df.iterrows()):
        o, h, l, c = row['Open'], row['High'], row['Low'], row['Close']
        color = color_up if c >= o else color_down
        ax.plot([i, i], [l, h], color=color, linewidth=width_wick * 6, solid_capstyle='round')
        body_low = min(o, c)
        body_high = max(o, c)
        body_h = max(body_high - body_low, (h - l) * 0.01)
        rect = Rectangle((i - width_body / 2, body_low), width_body, body_h,
                          facecolor=color, edgecolor=color, linewidth=0.5)
        ax.add_patch(rect)

    # MA 라인
    x_range = np.arange(len(df))
    ma_styles = [
        ('MA5', '#f59e0b', 1.2, 'MA5'),
        ('MA20', '#8b5cf6', 1.2, 'MA20'),
        ('MA60', '#06b6d4', 1.2, 'MA60'),
    ]
    for col, color, lw, label in ma_styles:
        vals = df[col].values
        mask = ~np.isnan(vals)
        if mask.sum() > 1:
            ax.plot(x_range[mask], vals[mask], color=color, linewidth=lw,
                    alpha=0.8, label=label)

    ax.legend(loc='upper left', fontsize=7, framealpha=0.8, edgecolor='#e2e8f0',
              handlelength=1.5, labelspacing=0.3)

    # 캔들 X축 숨기기 (거래량 축에 표시)
    ax.set_xticks([])

    # Y축
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'{x:,.0f}'))
    ax.tick_params(axis='y', labelsize=8, labelcolor='#64748b')

    ax.set_xlim(-1, len(df))
    ax.grid(axis='y', alpha=0.2, linestyle='--', color='#cbd5e1')
    ax.set_axisbelow(True)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['left'].set_color('#e2e8f0')
    ax.spines['bottom'].set_visible(False)

    # 마지막 종가 - X축 바로 위에 표시
    last = df.iloc[-1]
    prev = df.iloc[-2]
    chg = (last['Close'] - prev['Close']) / prev['Close'] * 100
    sign = '+' if chg >= 0 else ''
    color_last = color_up if chg >= 0 else color_down
    y_bottom = ax.get_ylim()[0]
    ax.text(len(df) - 1, y_bottom, f"{last['Close']:,.0f} ({sign}{chg:.1f}%)",
            fontsize=10, fontweight='bold', color=color_last, ha='center', va='bottom',
            bbox=dict(boxstyle='round,pad=0.2', facecolor='white', edgecolor=color_last, alpha=0.9, linewidth=1))

    # === 거래량 바 ===
    vol_colors = [color_up if df.iloc[i]['Close'] >= df.iloc[i]['Open'] else color_down
                  for i in range(len(df))]
    ax_vol.bar(x_range, df['Volume'].values, width=0.55, color=vol_colors, alpha=0.5)

    ax_vol.set_xlim(-1, len(df))
    ax_vol.set_axisbelow(True)
    ax_vol.grid(axis='y', alpha=0.15, linestyle='--', color='#cbd5e1')
    ax_vol.spines['top'].set_visible(False)
    ax_vol.spines['right'].set_visible(False)
    ax_vol.spines['left'].set_color('#e2e8f0')
    ax_vol.spines['bottom'].set_color('#e2e8f0')
    ax_vol.tick_params(axis='y', labelsize=7, labelcolor='#94a3b8')
    ax_vol.yaxis.set_major_formatter(plt.FuncFormatter(
        lambda x, p: f'{x/1e6:.0f}M' if x >= 1e6 else f'{x/1e3:.0f}K'))

    # X축 날짜 라벨 (거래량 축에 표시)
    tick_positions = list(range(0, len(df) - 1, max(1, len(df) // 5)))
    tick_positions.append(len(df) - 1)
    ax_vol.set_xticks(tick_positions)
    labels = []
    for idx in tick_positions:
        lbl = df.index[idx].strftime('%m/%d')
        if idx == len(df) - 1:
            lbl = df.index[idx].strftime('%m/%d') + '\n(today)'
        labels.append(lbl)
    ax_vol.set_xticklabels(labels, fontsize=9, color='#64748b')
    # 당일 라벨 강조
    tick_labels = ax_vol.get_xticklabels()
    if tick_labels:
        tick_labels[-1].set_fontsize(11)
        tick_labels[-1].set_fontweight('bold')
        tick_labels[-1].set_color('#ef4444')

    fig.savefig(out_path, facecolor='white', bbox_inches='tight', pad_inches=0.08)
    plt.close(fig)
    print(f'  saved: {out_path}')


def generate_candle_charts(output_dir):
    os.makedirs(output_dir, exist_ok=True)

    print('[CANDLE] KOSPI chart generating...')
    kospi = fetch_ohlcv('KOSPI', 80)
    draw_single_candle(kospi, os.path.join(output_dir, 'candle_kospi.png'))

    print('[CANDLE] KOSDAQ chart generating...')
    kosdaq = fetch_ohlcv('KOSDAQ', 80)
    draw_single_candle(kosdaq, os.path.join(output_dir, 'candle_kosdaq.png'))


if __name__ == '__main__':
    if len(sys.argv) > 1:
        output_dir = sys.argv[1]
    else:
        today = datetime.now().strftime('%Y-%m-%d')
        output_dir = os.path.join('output', today)
    generate_candle_charts(output_dir)

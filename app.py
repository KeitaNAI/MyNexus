import streamlit as st
import feedparser
import pandas as pd
import os
import urllib.parse
from datetime import datetime
import time
import base64

# --- Configuration ---
st.set_page_config(
    page_title="My Nexus Intelligence",
    layout="wide",
    initial_sidebar_state="expanded"
)

import re
from bs4 import BeautifulSoup
from newspaper import Article, Config
import nltk

# Ensure NLTK data is downloaded
try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    nltk.download('punkt')

# --- Constants ---

# Group A: Competitors (Unchanged)
GROUP_A_KEYWORDS = [
    "三菱商事 ヘルスケア",
    "伊藤忠商事 ヘルスケア",
    "住友商事 ヘルスケア",
    "丸紅 ヘルスケア"
]

# Group B: Mitsui (Broad Search + IHH)
# Logic: "Quality < Quantity" - Catch all relevant news including IHH
GROUP_B_QUERY = '(三井物産 AND (ウェルネス OR ヘルスケア OR 医療 OR 病院 OR 介護 OR 薬 OR 未病)) OR "IHHヘルスケア" OR "IHH Healthcare"'

# Group C: DTx / Digital Health (New)
GROUP_C_KEYWORDS = [
    "DTx",
    "デジタルセラピューティクス",
    "治療用アプリ",
    "デジタルヘルス",
    "CureApp",
    "サスメド",
    "Welby",
    "住友ファーマ DTx"
]

CLIPPED_NEWS_FILE = "clipped_news.csv"

# --- Functions ---

def get_base64_of_bin_file(bin_file):
    with open(bin_file, 'rb') as f:
        data = f.read()
    return base64.b64encode(data).decode()

def set_css_background():
    '''
    Sets a deep space CSS background with stars using radial gradients.
    '''
    page_bg_css = '''
    <style>
    .stApp {
        background-color: #050505;
        background-image: 
            radial-gradient(white, rgba(255,255,255,.2) 2px, transparent 3px),
            radial-gradient(white, rgba(255,255,255,.15) 1px, transparent 2px),
            radial-gradient(white, rgba(255,255,255,.1) 2px, transparent 3px);
        background-size: 550px 550px, 350px 350px, 250px 250px;
        background-position: 0 0, 40px 60px, 130px 270px;
        background-attachment: fixed;
    }
    
    /* Custom Title */
    h1 {
        font-family: 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
        text-transform: uppercase;
        background: linear-gradient(90deg, #00E5FF, #BF55EC);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        text-shadow: 0 0 10px rgba(0, 229, 255, 0.5);
        font-weight: 800;
        letter-spacing: 2px;
    }
    
    /* Buttons */
    .stButton > button {
        background-color: transparent !important;
        border: 2px solid #00E5FF !important;
        color: #00E5FF !important;
        border-radius: 5px;
        font-weight: bold;
        transition: all 0.3s ease;
    }
    .stButton > button:hover {
        background-color: #00E5FF !important;
        color: #000 !important;
        box-shadow: 0 0 15px #00E5FF;
    }
    
    /* Sidebar */
    section[data-testid="stSidebar"] {
        background-color: rgba(14, 17, 23, 0.95) !important;
        border-right: 1px solid #00E5FF;
    }
    
    /* News Item Text */
    div[data-testid="stVerticalBlock"] > div > div {
        color: #E0E0E0;
    }
    </style>
    '''
    st.markdown(page_bg_css, unsafe_allow_html=True)

def strip_html(text):
    """Removes HTML tags from text using BeautifulSoup."""
    if not text:
        return ""
    soup = BeautifulSoup(text, "html.parser")
    return soup.get_text(separator=" ", strip=True)

def get_news(query, limit=30):
    """Fetches news from Google News RSS for a given query."""
    # Append 'when:90d' to force recent news (last 3 months)
    # This prevents Google from showing "most relevant" but 6-month old news
    query_with_time = f"{query} when:90d"
    encoded_query = urllib.parse.quote(query_with_time)
    
    # Added num param roughly and forced date sorting with scoring=n
    # Note: 'when:90d' is part of the query 'q', 'scoring=n' helps with sorting of results within that range
    rss_url = f"https://news.google.com/rss/search?q={encoded_query}&hl=ja&gl=JP&ceid=JP:ja&scoring=n&num={limit}"
    feed = feedparser.parse(rss_url)
    news_list = []
    
    # Process up to 'limit' entries
    entries = feed.entries[:limit]
    
    for entry in entries:
        # Parse date
        if hasattr(entry, 'published_parsed') and entry.published_parsed:
            dt = datetime.fromtimestamp(time.mktime(entry.published_parsed))
        else:
            dt = datetime.now()

        # Extract & Clean Summary
        raw_summary = entry.summary if hasattr(entry, 'summary') else ""
        clean_summary = strip_html(raw_summary)

        news_list.append({
            "Title": entry.title,
            "Link": entry.link,
            "Published_Date_Obj": dt,
            "Published_Date_Str": dt.strftime("%Y年%m月%d日 %H:%M"),
            "Source": entry.source.title if hasattr(entry, 'source') else "Google News",
            "Keyword": query,
            "Summary": clean_summary,
            "Is_AI_Pick": False # Deprecated, kept for schema compatibility
        })
    return news_list

def load_saved_news():
    """Loads saved news from CSV."""
    if os.path.exists(CLIPPED_NEWS_FILE):
        return pd.read_csv(CLIPPED_NEWS_FILE)
    else:
        # Schema updated to include AI Pick status (Legacy support)
        return pd.DataFrame(columns=["Title", "Link", "Published_Date", "Keyword", "Saved_Date", "Is_AI_Pick"])

def save_to_csv(news_item):
    """Saves a single news item to CSV, avoiding duplicates."""
    df = load_saved_news()
    
    # Check for duplicates based on Link
    if not df.empty and news_item["Link"] in df["Link"].values:
        return False # Already saved

    # Prepare save data
    save_data = {
        "Title": news_item["Title"],
        "Link": news_item["Link"],
        "Published_Date": news_item["Published_Date_Str"],
        "Keyword": news_item["Keyword"],
        "Saved_Date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "Is_AI_Pick": news_item["Is_AI_Pick"]
    }

    new_row = pd.DataFrame([save_data])
    
    # Append to file
    if not os.path.exists(CLIPPED_NEWS_FILE):
        new_row.to_csv(CLIPPED_NEWS_FILE, index=False, encoding='utf-8-sig')
    else:
        new_row.to_csv(CLIPPED_NEWS_FILE, mode='a', header=False, index=False, encoding='utf-8-sig')
    
    return True

def display_news_list(news_list):
    """Helper to display a list of news dictionaries."""
    if not news_list:
        st.warning("No news found.")
        return

    # De-duplicate listing in UI
    seen_links = set()
    unique_news = []
    for item in news_list:
        if item['Link'] not in seen_links:
            unique_news.append(item)
            seen_links.add(item['Link'])

    # Sort Priority: Strictly by Date (Newest first)
    unique_news.sort(key=lambda x: x['Published_Date_Obj'], reverse=True)
            
    st.write(f"Found {len(unique_news)} articles.")

    for i, item in enumerate(unique_news):
        with st.container():
            col1, col2 = st.columns([0.85, 0.15])
            with col1:
                # 1. Title
                st.subheader(item['Title'])
                
                # 2. Metadata
                st.caption(f"**Source:** {item['Source']} | **Date:** {item['Published_Date_Str']} | **Keyword:** {item['Keyword']}")
                
                # 3. Smart Summary Display
                summary_text = item.get('Summary', '').strip()
                title_text = item['Title'].strip()
                
                show_summary = False
                if summary_text:
                    # Condition 1: Length check (at least 20 chars)
                    if len(summary_text) >= 20:
                        # Condition 2: Deduplication
                        # Check if summary is practically identical to title or just contains title with little else
                        if summary_text == title_text:
                            show_summary = False
                        elif summary_text.startswith(title_text):
                            show_summary = False
                        elif title_text in summary_text and len(summary_text) < len(title_text) * 1.5:
                            show_summary = False
                        else:
                            show_summary = True
                
                if show_summary:
                    st.write(summary_text)
                
                # 4. Actions: Read Article & Deep Dive
                action_cols = st.columns([0.2, 0.8])
                with action_cols[0]:
                    st.markdown(f"[Read Article 🔗]({item['Link']})")
                
                with action_cols[1]:
                    if st.button("Deep Dive 🧠", key=f"deep_dive_{i}"):
                        with st.spinner("Analyzing article..."):
                            try:
# ユーザーエージェントを設定（ブラウザのふりをする）
                                config = Config()
                                config.browser_user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36'
                                config.request_timeout = 10

                                article = Article(item['Link'], config=config, language='ja')
                                article.download()
                                article.parse()
                                article.nlp()
# 【変更点】要約が空っぽなら、本文の冒頭を表示する「保険」をかける
                                if article.summary:
                                    st.success("AI Summary:")
                                    st.info(article.summary)
                                elif article.text:
                                    st.warning("Summary failed. Showing article excerpt:")
                                    st.info(article.text[:400] + "...") # 本文の最初の400文字を表示
# サイトの中身が取れない場合は、RSSの要約を表示する
                                    st.warning("Site protected. Showing RSS summary:")
                                    st.info(item.get('summary', 'No summary available.'))
                            except Exception as e:
                                st.error(f"Could not summarize article: {e}")

            with col2:
                save_key = f"save_{i}_{item['Link']}"
                if st.button("Clip 📌", key=save_key):
                    success = save_to_csv(item)
                    if success:
                        st.toast(f"Saved", icon="✅")
                    else:
                        st.toast("Already saved", icon="ℹ️")
            st.divider()

# --- Main App ---

def main():
    # Inject CSS
    set_css_background()

    st.title("My Nexus Intelligence") 
    
    # Sidebar
    st.sidebar.title("Navigation")
    app_mode = st.sidebar.radio("Go to", [
        "A: 総合商社ヘルスケア",
        "B: 三井物産ヘルスケア",
        "C: DTx / デジタルヘルス",
        "Saved Articles"
    ])

    if app_mode == "A: 総合商社ヘルスケア":
        st.header("A: 総合商社ヘルスケア")
        st.caption("Searching for: " + ", ".join([k.split()[0] for k in GROUP_A_KEYWORDS]))
        
        all_news = []
        with st.spinner("Fetching Group A news..."):
            for keyword in GROUP_A_KEYWORDS:
                all_news.extend(get_news(keyword))
        
        display_news_list(all_news)

    elif app_mode == "B: 三井物産ヘルスケア":
        st.header("B: 三井物産ヘルスケア")
        st.caption(f"Broad Search Mode: {GROUP_B_QUERY}")
        
        all_news = []
        with st.spinner(f"Fetching news for Broad Query..."):
            # Using the single broad query + increased limit
            all_news.extend(get_news(GROUP_B_QUERY, limit=30))
                
        display_news_list(all_news)

    elif app_mode == "C: DTx / デジタルヘルス":
        st.header("C: DTx / デジタルヘルス")
        st.caption("Searching for: " + ", ".join(GROUP_C_KEYWORDS))
        
        all_news = []
        with st.spinner("Fetching Group C news..."):
            for keyword in GROUP_C_KEYWORDS:
                all_news.extend(get_news(keyword))
        
        display_news_list(all_news)

    elif app_mode == "Saved Articles":
        st.header("Saved Articles (Clipped)")
        df = load_saved_news()
        if df.empty:
            st.info("No saved articles yet.")
        else:
            st.dataframe(df)
            
            csv = df.to_csv(index=False).encode('utf-8-sig')
            st.download_button(
                "Download CSV",
                csv,
                "my_clipped_news.csv",
                "text/csv",
                key='download-csv'
            )

if __name__ == "__main__":
    main()

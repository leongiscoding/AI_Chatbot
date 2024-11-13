import streamlit as st
import os
import google.generativeai as genai
from functools import lru_cache
import requests
from bs4 import BeautifulSoup
from typing import List, Optional, Dict, Tuple
from dataclasses import dataclass
import logging
from time import sleep
from concurrent.futures import ThreadPoolExecutor
import aiohttp
import asyncio
from datetime import datetime, timedelta
import urllib.parse

# Set up logging with more detailed configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('gamers_compass.log')
    ]
)
logger = logging.getLogger(__name__)

@dataclass
class GameInfo:
    """Data class to store game information with metadata"""
    content: List[str]
    timestamp: datetime = datetime.now()
    source: Optional[str] = None
    category: Optional[str] = None
    error: Optional[str] = None

class CacheManager:
    """Handle caching of requests and responses"""
    def __init__(self, cache_duration: int = 3600):
        self.cache = {}
        self.cache_duration = cache_duration

    def get(self, key: str) -> Optional[GameInfo]:
        if key in self.cache:
            info, timestamp = self.cache[key]
            if datetime.now() - timestamp < timedelta(seconds=self.cache_duration):
                return info
            del self.cache[key]
        return None

    def set(self, key: str, value: GameInfo):
        self.cache[key] = (value, datetime.now())

        
def deduplicate_snippets(snippets: List[str]) -> List[str]:
    """Remove duplicate snippets based on content similarity."""
    unique_snippets = []
    seen = set()
    for snippet in snippets:
        if snippet not in seen:
            unique_snippets.append(snippet)
            seen.add(snippet)
    return unique_snippets
class GamersCompass:
    """Enhanced main class to handle the Gamers Compass application"""
    
    CATEGORIES = {
        "Installation": "🔧",
        "Guideline": "📖",
        "Review": "⭐",
        "Speedrun": "⚡",
        "News": "📰",
        "Mods": "🔨",
        "Tips & Tricks": "💡",
        "Community": "👥"
    }
    
    def __init__(self):
        self.api_key = self._setup_api_key()
        self.cache_manager = CacheManager()
        self.session = aiohttp.ClientSession()
        
        if self.api_key:
            genai.configure(api_key=self.api_key)
            self.generation_config = {
                "temperature": 0.7,  # Reduced for more consistent outputs
                "top_p": 0.95,
                "top_k": 40,
                "max_output_tokens": 1024,
                "response_mime_type": "text/plain",
            }

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.session.close()
    
    @staticmethod
    def _setup_api_key() -> Optional[str]:
        """Set up and validate API key with enhanced error handling"""
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            st.error("""
                Google API key is not set. Please set the GOOGLE_API_KEY environment variable.
                You can get an API key from the Google Cloud Console.
                """)
            logger.error("API key not found in environment variables")
            return None
        return api_key

    async def scrape_game_info_async(self, game_name: str, category: str) -> List[str]:
        """Asynchronously scrape game information from multiple sources."""
        search_url = f"https://www.google.com/search?q={game_name}+{category.lower()}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"
        }
        
        try:
            async with self.session.get(search_url, headers=headers, timeout=10) as response:
                if response.status == 200:
                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    snippets = self.deduplicate_snippets([
                        result.text 
                        for result in soup.find_all("div", class_="BNeawe s3v9rd AP7Wnd")
                    ])[:5]  # Increase the number of snippets
                    
                    return snippets if snippets else ["No relevant information found."]
                else:
                    logger.warning(f"HTTP {response.status} when scraping {search_url}")
                    return ["Unable to retrieve information due to server response."]
                    
        except Exception as e:
            logger.error(f"Error scraping data: {str(e)}", exc_info=True)
            return [f"Unable to retrieve information: {str(e)}"]

    def deduplicate_snippets(self, snippets: List[str]) -> List[str]:
        """Remove duplicate snippets from the list."""
        return list(set(snippets))
    
    async def scrape_news(self, game_name: str):
        # Replace spaces with hyphens for URLs
        game_name = game_name.replace(" ", "-")
        # Encode other special characters in the game name
        encoded_game_name = urllib.parse.quote(game_name)
        
        url = f"https://sea.ign.com/{encoded_game_name}"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    text = await response.text()
                    soup = BeautifulSoup(text, "html.parser")
                    news_section = soup.find_all("article")
                    
                    news_items = []
                    for article in news_section:
                        headline = article.find("h3")
                        if headline:
                            news_items.append(headline.text.strip())
                    
                    return news_items
                else:
                    return "Incorrect Game Title!"

    async def scrape_guides(self, game_name: str):
        # Replace spaces with hyphens for URLs
        game_name = game_name.replace(" ", "-")
        # Encode other special characters in the game name
        encoded_game_name = urllib.parse.quote(game_name)
        
        url = f"https://sea.ign.com/{encoded_game_name}"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    text = await response.text()
                    soup = BeautifulSoup(text, "html.parser")
                    guide_section = soup.find_all("article")
                    
                    guide_items = []
                    for article in guide_section:
                        headline = article.find("h3")
                        if headline:
                            guide_items.append(headline.text.strip())
                    
                    return guide_items
                else:
                    return "Incorrect Game Title!"


    async def close(self):
        """Close the aiohttp session."""
        await self.session.close()

    async def get_game_content_async(self, category: str, game_name: str) -> GameInfo:
        """Asynchronously get game content with enhanced error handling and caching"""
        cache_key = f"{category}_{game_name}"
        cached_result = self.cache_manager.get(cache_key)
        
        if cached_result:
            return cached_result
        
        try:
            snippets = await self.scrape_game_info_async(game_name, category)
            
            # 处理 "news" 或 "guideline" 类别
            if category.lower() in ["guideline", "news"]:
                result = GameInfo(
                    content=snippets,
                    category=category,
                    source="web_scraping"
                )
            else:
                # 对于其他类别，使用生成模型
                prompt = self._generate_prompt(category, game_name, snippets[0])
                
                model = genai.GenerativeModel(
                    model_name="gemini-1.5-flash",
                    generation_config=self.generation_config
                )
                response = model.generate_content(prompt)
                
                result = GameInfo(
                    content=[response.text] if response else ['No content available'],
                    category=category,
                    source="gemini"
                )
            
            self.cache_manager.set(cache_key, result)
            return result
            
        except Exception as e:
            error_msg = f"Error generating content: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return GameInfo(content=[], error=error_msg)


    def _generate_prompt(self, category: str, game_name: str, context: str) -> str:
        """Generate more specific and structured prompts based on category"""
        prompts = {
            "Installation": f"Provide step-by-step installation instructions for {game_name}, including system requirements and common troubleshooting tips. Context: {context}",
            "Guideline": f"Provide a detailed gameplay guide for {game_name}. Focus on key areas such as getting started effectively, building characters or skills optimally, and strategic tips for progressing through critical game stages. Context: {context}",
            "News": f"Summarize the latest news and updates about {game_name}, including new releases, patches, upcoming events, or developer announcements. Context: {context}",
            "Review": f"Create a comprehensive review of {game_name} covering gameplay, graphics, story, and value for money. Include both pros and cons. Context: {context}",
            "Speedrun": f"Explain the main speedrunning strategies and current records for {game_name}, including key techniques and shortcuts. Context: {context}",
            "Mods": f"List and describe the most popular and essential mods for {game_name}, including installation instructions. Context: {context}",
            "Tips & Tricks": f"Share advanced tips, secret techniques, and strategic advice for mastering {game_name}. Context: {context}",
            "Community": f"Describe the active community spaces, events, and resources for {game_name} players. Context: {context}"
        }
        
        return prompts.get(category, f"Provide {category.lower()} information for {game_name}. Context: {context}")

    def render_category_buttons(self):
        """Render category selection buttons with improved layout"""
        st.write("### Select a Category")
        
        # Create two rows of buttons for better layout
        rows = [list(self.CATEGORIES.items())[i:i + 4] for i in range(0, len(self.CATEGORIES), 4)]
        
        for row in rows:
            cols = st.columns(4)
            for idx, (category, emoji) in enumerate(row):
                with cols[idx]:
                    if st.button(
                        f"{emoji} {category}",
                        key=f"cat_{category}",
                        use_container_width=True
                    ):
                        st.session_state.selected_category = category

    async def render_game_content(self, game_name: str, category: str):
        """Render game content section with enhanced UI and error handling"""
        st.subheader(f"{self.CATEGORIES[category]} {category} for {game_name}")
        
        with st.spinner('Loading content...'):
            if category.lower() == "news":
                # Scrape news content from GameSpot
                news_content = await self.scrape_news(game_name)
                
                if isinstance(news_content, str):  # Check if it's an error message
                    st.warning(news_content)
                    return

                # Display up to 5 news articles
                for idx, article in enumerate(news_content[:5]):  # Limit to 5 articles
                    with st.expander(f"News Article {idx + 1}", expanded=idx == 0):
                        st.write(article)
                        if st.button("Get More Details", key=f"news_details_{idx}"):
                            with st.spinner("Fetching detailed information..."):
                                detailed_info = await self.get_game_content_async("Detailed Info", article)
                                st.write(detailed_info.content[0] if detailed_info.content else "No details available")

            elif category.lower() == "guideline":
                # Scrape game guides from GameSpot
                guides_content = await self.scrape_guides(game_name)

                if isinstance(guides_content, str):  # Check if it's an error message
                    st.warning(guides_content)
                    return

                # Display up to 5 game guides
                for idx, guide in enumerate(guides_content[:5]):  # Limit to 5 guides
                    with st.expander(f"Game Guide {idx + 1}", expanded=idx == 0):
                        st.write(guide)
                        if st.button("Get More Details", key=f"guideline_details_{idx}"):
                            with st.spinner("Fetching detailed information..."):
                                detailed_info = await self.get_game_content_async("Detailed Info", guide)
                                st.write(detailed_info.content[0] if detailed_info.content else "No details available")

            else:
                # For other categories, fetch the content normally
                result = await self.get_game_content_async(category, game_name)
                
                if result.error:
                    st.error(f"Error: {result.error}")
                    st.button("Try Again", key="retry")
                    return
                
                if not result.content:
                    st.warning("No content available.")
                    return

                # Display the content for other categories
                st.markdown(result.content[0])

            # Add feedback buttons for all categories
            col1, col2 = st.columns(2)
            with col1:
                if st.button("👍 Helpful", key="helpful"):
                    st.success("Thank you for your feedback!")
            with col2:
                if st.button("👎 Not Helpful", key="not_helpful"):
                    st.text_area("How can we improve?", key="feedback")
                    if st.button("Submit Feedback"):
                        st.success("Thank you for your feedback!")


    async def render_custom_query_section(self, game_name: str):
        """Render enhanced custom query input section"""
        st.divider()
        st.subheader("🔍 Custom Query")
        
        # Add query suggestions
        suggestions = [
            "What are the best builds for beginners?",
            "How to unlock all achievements?",
            "What are the hidden Easter eggs?",
            "Which DLCs are worth buying?",
            "How to beat the final boss?"
        ]
        
        col1, col2 = st.columns([2, 1])
        with col1:
            user_input = st.text_area(
                "Enter your specific query:",
                help="Be as specific as possible for better results"
            )
        with col2:
            st.write("Suggested queries:")
            for suggestion in suggestions:
                if st.button(suggestion, key=f"suggest_{suggestion}"):
                    user_input = suggestion
        
        if user_input:
            custom_prompt = f"{user_input} for the game {game_name}"
            with st.spinner('Generating custom content...'):
                result = await self.get_game_content_async("Custom Query", custom_prompt)
                
                if result.error:
                    st.error(f"Error: {result.error}")
                elif result.content:
                    st.markdown(result.content[0])
                    
                    # Add source citation
                    if result.source:
                        st.caption(f"Popular Search: {result.source}")
                else:
                    st.warning("No additional content could be generated for your query.")

async def main():
    """Asynchronous main application function with enhanced UI"""
    st.set_page_config(
        page_title="Gamers Compass",
        page_icon="🎮",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    
    async with GamersCompass() as app:
        if not app.api_key:
            st.stop()
        
        st.title("🎮 Gamers Compass")
        st.markdown("""
            Your ultimate guide to gaming information! Get instant access to:
            - Installation guides and troubleshooting
            - Game reviews and ratings
            - Speedrunning strategies
            - Mods and custom content
            - Tips & tricks from the community
        """)
        
        app.render_category_buttons()
        
        if "selected_category" in st.session_state:
            selected_category = st.session_state.selected_category
            
            game_name = st.text_input(
                "🎲 Enter game name:",
                placeholder="e.g., The Legend of Zelda: Breath of the Wild",
                help="Enter the full name of the game for best results"
            )
            
            if game_name:
                await app.render_game_content(game_name, selected_category)
                await app.render_custom_query_section(game_name)
        
        # Add footer
        st.markdown("---")
        st.markdown(
            "Made with ❤️ by Gamers Compass Team | "
            "[Report Bug](/) | [Suggest Feature](/) | [GitHub](/)"
        )

if __name__ == "__main__":
    asyncio.run(main())

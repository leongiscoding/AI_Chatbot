import streamlit as st
import os
import google.generativeai as genai
from functools import lru_cache
import requests
from bs4 import BeautifulSoup

# Configure the Gemini API key with error handling
api_key = os.getenv("GOOGLE_API_KEY")
api_key = st.secrets["google"]["api_key"]
if not api_key:
    st.error("Google API key is not set. Please provide a valid API key.")
    st.stop()

genai.configure(api_key=api_key)

# Create the model with the generation configuration
generation_config = {
    "temperature": 1,
    "top_p": 0.95,
    "top_k": 40,
    "response_mime_type": "text/plain",
}

# Function to scrape game information
def scrape_game_info(game_name, category):
    search_url = f"https://www.google.com/search?q={game_name}+{category.lower()}"
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        response = requests.get(search_url, headers=headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        # Extract relevant text snippets
        snippets = []
        for result in soup.find_all("div", class_="BNeawe s3v9rd AP7Wnd"):
            snippets.append(result.text)

        # Limit to top 3 snippets
        return snippets[:3] if snippets else ["No relevant information found."]

    except requests.RequestException as e:
        st.error(f"Error occurred while fetching data: {e}")
        return ["Unable to retrieve information."]

# Cache the results to prevent repeated API calls
@lru_cache(maxsize=10)
def get_game_content(category, game_name):
    if category.lower() in ["guideline", "news"]:
        # Scrape the top 3 snippets for Guideline or News
        snippets = scrape_game_info(game_name, category)
        return snippets
    else:
        # Regular content generation for other categories
        scraped_info = scrape_game_info(game_name, category)[0]
        prompt = f"Based on the latest online information below, provide {category.lower()} details for {game_name}:\n\n{scraped_info}\n\nPlease summarize and structure it in an informative manner."

        try:
            model = genai.GenerativeModel(
                model_name="gemini-1.5-flash",
                generation_config=generation_config
            )
            response = model.generate_content(prompt)
            return [response.text if response else 'No content available']
        
        except genai.exceptions.ApiError as e:
            st.error(f"API error occurred: {str(e)}")
            return [None]
        except Exception as e:
            st.error(f"An unexpected error occurred: {str(e)}")
            return [None]

def main():
    st.set_page_config(page_title="Guild Game AI Bot", page_icon="🎮")
    st.title("Guild Game AI Bot")
    st.write("Get information about your favorite games!")

    # Category selection using buttons
    categories = ["Installation", "Guideline", "Review", "Speedrun", "News"]
    selected_category = st.session_state.get("selected_category", None)

    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        if st.button("Installation"):
            st.session_state.selected_category = "Installation"
    with col2:
        if st.button("Guideline"):
            st.session_state.selected_category = "Guideline"
    with col3:
        if st.button("Review"):
            st.session_state.selected_category = "Review"
    with col4:
        if st.button("Speedrun"):
            st.session_state.selected_category = "Speedrun"
    with col5:
        if st.button("News"):
            st.session_state.selected_category = "News"

    if "selected_category" in st.session_state:
        selected_category = st.session_state.selected_category
        st.write(f"You selected: {selected_category}")

        # Input for game name
        game_name = st.text_input(f"Enter the name of the game for {selected_category.lower()}:")

        if not game_name:
            st.warning("Please enter a game name to proceed.")
            return

# Inside your main function where you display the buttons
        if game_name:
            st.subheader(f"{selected_category} for {game_name}")

            with st.spinner('Loading content...'):
                content = get_game_content(selected_category, game_name)
                if content:
                    if selected_category.lower() in ["guideline", "news"]:
                        # Display top 3 snippets as buttons with unique keys
                        for index, snippet in enumerate(content):
                            if st.button(snippet, key=f"{selected_category}_{index}"):
                                st.subheader("Detailed Information")
                                detailed_info = get_game_content("Detailed Info", snippet)[0]
                                st.write(detailed_info)
                    else:
                        st.write(content[0])


            # Additional section for user input
            st.write("If you couldn't find the information you were looking for, you can specify it below:")
            user_input = st.text_area("Enter your specific query or information request:")

            if user_input:
                st.write("Thank you for your input! Here's the information related to your query:")
                # Attempt to generate related content using the user's input
                custom_prompt = f"{user_input} for the game {game_name}"
                with st.spinner('Generating custom content...'):
                    additional_content = get_game_content("Custom Query", custom_prompt)
                    if additional_content:
                        st.write(additional_content[0])
                    else:
                        st.write("Sorry, we couldn't generate any additional content for your query.")

if __name__ == "__main__":
    main()

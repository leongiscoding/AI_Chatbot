import streamlit as st
import os
import google.generativeai as genai

# Configure the Gemini API key
genai.configure(api_key=st.secrets["google"]["api_key"])


# Create the model with the generation configuration
generation_config = {
    "temperature": 1,
    "top_p": 0.95,
    "top_k": 40,
    "max_output_tokens": 200,  # Adjusted to your needs
    "response_mime_type": "text/plain",
}

def get_game_content(category, game_name):
    prompt = f"Provide concise {category.lower()} information for the game {game_name} in a clear and informative manner."
    
    try:
        # Initialize the model
        model = genai.GenerativeModel(
            model_name="gemini-1.5-flash",
            generation_config=generation_config
        )
        
        # Start a chat session
        chat_session = model.start_chat(history=[])
        
        # Generate content using the chat session
        response = chat_session.send_message(prompt)
        
        # Extract and return the text content
        content = response.text if response else 'No content available'
        return content
    
    except Exception as e:
        st.error(f"An error occurred: {str(e)}")
        return None

def main():
    # Page configuration
    st.set_page_config(page_title="Gamer Assistant", page_icon="🎮")

    # Title
    st.title("Gamer Assistant")
    st.write("Get information about your favorite games!")

    # Category selection
    categories = ["Installation", "Guideline", "Review", "Speedrun", "News"]
    selected_category = st.selectbox("Select a category:", categories)

    if selected_category:
        st.write(f"You selected: {selected_category}")
        
        # Input for game name
        game_name = st.text_input(f"Enter the name of the game for {selected_category.lower()}:")
        
        #Optional, apply duckduckgo search right here
        if game_name:
            st.subheader(f"{selected_category} for {game_name}")
            content = get_game_content(selected_category, game_name)
            if content:
                st.write(content)

if __name__ == "__main__":
    main()

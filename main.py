import streamlit as st
import requests
import pandas as pd
from datetime import datetime
import os
from dotenv import load_dotenv
import re

# Load environment variables
load_dotenv()

# GitHub API configuration
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
HEADERS = {
    'Authorization': f'token {GITHUB_TOKEN}',
    'Accept': 'application/vnd.github.v3+json'
}

def check_rate_limit():
    """Check GitHub API rate limit"""
    try:
        response = requests.get('https://api.github.com/rate_limit', headers=HEADERS)
        if response.status_code == 200:
            data = response.json()
            core_limit = data['resources']['core']
            return core_limit['remaining'], core_limit['limit'], core_limit['reset']
        return None, None, None
    except:
        return None, None, None

def parse_github_pr_url(url):
    """Parse GitHub PR URL to extract owner, repo, and PR number"""
    pattern = r'https://github\.com/([^/]+)/([^/]+)/pull/(\d+)'
    match = re.match(pattern, url)
    if match:
        return match.groups()
    return None, None, None

def get_pr_reactions(owner, repo, pr_number):
    """Get all reactions for a GitHub PR with pagination and optimization"""
    try:
        # Get PR details first
        pr_url = f'https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}'
        pr_response = requests.get(pr_url, headers=HEADERS)
        
        if pr_response.status_code != 200:
            return None, f"Error fetching PR: {pr_response.status_code}"
        
        pr_data = pr_response.json()
        
        # Get all reactions for the PR with pagination
        all_reactions = []
        page = 1
        per_page = 100  # Maximum allowed per page
        
        while True:
            reactions_url = f'https://api.github.com/repos/{owner}/{repo}/issues/{pr_number}/reactions'
            params = {
                'page': page,
                'per_page': per_page
            }
            reactions_response = requests.get(reactions_url, headers=HEADERS, params=params)
            
            if reactions_response.status_code != 200:
                return None, f"Error fetching reactions: {reactions_response.status_code}"
            
            reactions_data = reactions_response.json()
            
            # If no more reactions, break the loop
            if not reactions_data:
                break
                
            all_reactions.extend(reactions_data)
            
            # If we got fewer results than per_page, we've reached the end
            if len(reactions_data) < per_page:
                break
                
            page += 1
        
        # Group reactions by user to avoid duplicate profile fetches
        user_reactions = {}
        for reaction in all_reactions:
            username = reaction['user']['login']
            if username not in user_reactions:
                user_reactions[username] = {
                    'user': reaction['user'],
                    'reactions': [],
                    'first_reaction_date': reaction['created_at']
                }
            
            user_reactions[username]['reactions'].append({
                'content': reaction['content'],
                'created_at': reaction['created_at']
            })
            
            # Keep track of the earliest reaction date for this user
            if reaction['created_at'] < user_reactions[username]['first_reaction_date']:
                user_reactions[username]['first_reaction_date'] = reaction['created_at']
        
        # Get user details for unique users only
        reactions_list = []
        total_users = len(user_reactions)
        
        # Create a progress bar placeholder
        progress_placeholder = st.empty()
        
        for i, (username, user_data) in enumerate(user_reactions.items()):
            # Update progress
            progress_placeholder.progress((i + 1) / total_users, f"Processing user {i + 1} of {total_users}: {username}")
            
            user = user_data['user']
            
            # Get user profile details with rate limit handling (only once per user)
            user_url = f"https://api.github.com/users/{user['login']}"
            user_response = requests.get(user_url, headers=HEADERS)
            
            if user_response.status_code == 200:
                profile_data = user_response.json()
                created_at = profile_data.get('created_at', 'N/A')
                if created_at != 'N/A':
                    # Keep full timestamp for better spam detection
                    created_at_full = datetime.strptime(created_at, '%Y-%m-%dT%H:%M:%SZ').strftime('%Y-%m-%d %H:%M:%S')
                    created_at_date_only = datetime.strptime(created_at, '%Y-%m-%dT%H:%M:%SZ').strftime('%Y-%m-%d')
                else:
                    created_at_full = 'N/A'
                    created_at_date_only = 'N/A'
            elif user_response.status_code == 403:
                # Rate limit exceeded
                st.warning(f"Rate limit exceeded while fetching user {user['login']}. Some profile creation dates may be missing.")
                created_at_full = 'Rate Limited'
                created_at_date_only = 'Rate Limited'
            else:
                created_at_full = 'N/A'
                created_at_date_only = 'N/A'
            
            # Get all reactions for this user as emojis
            user_reaction_emojis = [get_emoji_for_reaction(r['content']) for r in user_data['reactions']]
            reactions_str = ' '.join(user_reaction_emojis)
            
            # Use the earliest reaction date
            first_reaction_date = datetime.strptime(user_data['first_reaction_date'], '%Y-%m-%dT%H:%M:%SZ').strftime('%Y-%m-%d %H:%M:%S')
            
            reactions_list.append({
                'Reactions': reactions_str,
                'Reaction Count': len(user_data['reactions']),
                'Username': user['login'],
                'Profile URL': user['html_url'],
                'First Reaction Date': first_reaction_date,
                'Profile Creation Date': created_at_full,
                'Profile Creation Date (Date Only)': created_at_date_only  # For spam analysis
            })
        
        # Clear the progress bar
        progress_placeholder.empty()
        
        return reactions_list, None
        
    except Exception as e:
        return None, f"Error: {str(e)}"

def get_emoji_for_reaction(content):
    """Convert GitHub reaction content to emoji"""
    emoji_map = {
        '+1': '👍',
        '-1': '👎',
        'laugh': '😄',
        'confused': '😕',
        'heart': '❤️',
        'hooray': '🎉',
        'rocket': '🚀',
        'eyes': '👀'
    }
    return emoji_map.get(content, content)

def analyze_spam_potential(reactions_data, threshold_date):
    """Analyze potential spam accounts based on creation date"""
    spam_accounts = []
    legitimate_accounts = []
    unknown_accounts = []
    
    for user in reactions_data:
        creation_date = user['Profile Creation Date (Date Only)']  # Use date-only field for comparison
        
        if creation_date in ['N/A', 'Rate Limited']:
            unknown_accounts.append(user)
        else:
            try:
                user_creation = datetime.strptime(creation_date, '%Y-%m-%d')
                if user_creation >= threshold_date:
                    spam_accounts.append(user)
                else:
                    legitimate_accounts.append(user)
            except:
                unknown_accounts.append(user)
    
    return spam_accounts, legitimate_accounts, unknown_accounts

def create_clickable_username(username, profile_url):
    """Create clickable username link"""
    return f'<a href="{profile_url}" target="_blank">{username}</a>'

# Streamlit app
def main():
    st.set_page_config(page_title="GitHub PR Reactions Dashboard", page_icon="🔍", layout="wide")
    
    # Initialize session state
    if 'reactions_data' not in st.session_state:
        st.session_state.reactions_data = None
    if 'current_pr_url' not in st.session_state:
        st.session_state.current_pr_url = ""
    if 'loading' not in st.session_state:
        st.session_state.loading = False
    
    st.title("🔍 GitHub PR Reactions Dashboard")
    st.markdown("Enter a GitHub Pull Request URL to analyze all reactions and user profiles.")
    
    # Display rate limit information
    if GITHUB_TOKEN:
        remaining, limit, reset_time = check_rate_limit()
        if remaining is not None:
            col1, col2 = st.columns(2)
            with col1:
                st.info(f"API Rate Limit: {remaining}/{limit} requests remaining")
            with col2:
                reset_dt = datetime.fromtimestamp(reset_time)
                st.info(f"Resets at: {reset_dt.strftime('%H:%M:%S')}")
    
    # Input field for GitHub PR URL
    pr_url = st.text_input(
        "GitHub PR URL:",
        value=st.session_state.current_pr_url,
        placeholder="https://github.com/owner/repo/pull/123",
        help="Enter the full URL of a GitHub Pull Request"
    )
    
    # Button to analyze reactions
    col1, col2 = st.columns([1, 4])
    with col1:
        analyze_clicked = st.button("Analyze Reactions", type="primary")
    with col2:
        if st.session_state.reactions_data is not None:
            if st.button("Clear Data", type="secondary"):
                st.session_state.reactions_data = None
                st.session_state.current_pr_url = ""
                st.rerun()
    
    # Check if we need to fetch new data
    should_fetch = analyze_clicked and pr_url != st.session_state.current_pr_url
    
    if analyze_clicked:
        if not pr_url:
            st.error("Please enter a GitHub PR URL")
            return
        
        if not GITHUB_TOKEN:
            st.error("GitHub token not found. Please set GITHUB_TOKEN in your .env file")
            return
        
        # Parse the URL
        owner, repo, pr_number = parse_github_pr_url(pr_url)
        
        if not all([owner, repo, pr_number]):
            st.error("Invalid GitHub PR URL format. Please use: https://github.com/owner/repo/pull/123")
            return
        
        # Only fetch if URL changed or no data exists
        if should_fetch or st.session_state.reactions_data is None:
            st.info(f"Analyzing PR #{pr_number} from {owner}/{repo}...")
            
            # Get reactions
            with st.spinner("Fetching reactions and user profiles..."):
                reactions, error = get_pr_reactions(owner, repo, pr_number)
            
            if error:
                st.error(error)
                return
            
            if not reactions:
                st.warning("No reactions found for this PR")
                return
            
            # Store in session state
            st.session_state.reactions_data = reactions
            st.session_state.current_pr_url = pr_url
    
    # Display results if we have data
    if st.session_state.reactions_data is not None:
        reactions = st.session_state.reactions_data
        
        # Spam Analysis Section
        st.subheader("🚨 Spam Detection Analysis")
        
        col1, col2 = st.columns([2, 3])
        with col1:
            # Date picker for spam threshold
            default_date = datetime(2025, 10, 1).date()
            spam_threshold_date = st.date_input(
                "Accounts created after this date are flagged as potential spam:",
                value=default_date,
                help="Users who created their GitHub accounts after this date will be flagged as potentially suspicious",
                key="spam_threshold"
            )
        
        with col2:
            st.info("💡 **Tip**: Recent account creation doesn't necessarily mean spam, but it's worth investigating accounts created very recently that are actively reacting to PRs.")
        
        # Convert to datetime for analysis
        threshold_datetime = datetime.combine(spam_threshold_date, datetime.min.time())
        
        # Analyze spam potential
        spam_accounts, legitimate_accounts, unknown_accounts = analyze_spam_potential(reactions, threshold_datetime)
        
        # Spam gauge metrics
        total_users = len(reactions)
        spam_count = len(spam_accounts)
        legitimate_count = len(legitimate_accounts)
        unknown_count = len(unknown_accounts)
        
        # Calculate spam percentage
        spam_percentage = (spam_count / total_users * 100) if total_users > 0 else 0
        
        # Display spam gauge
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            # Spam gauge with color coding
            if spam_percentage <= 10:
                gauge_color = "🟢"
                risk_level = "LOW"
            elif spam_percentage <= 25:
                gauge_color = "🟡"
                risk_level = "MEDIUM"
            else:
                gauge_color = "🔴"
                risk_level = "HIGH"
            
            st.metric(
                f"{gauge_color} Spam Risk",
                f"{spam_percentage:.1f}%",
                delta=f"{risk_level} RISK",
                help=f"Percentage of users created after {spam_threshold_date}"
            )
        
        with col2:
            st.metric("🚩 Flagged Accounts", spam_count, help="Accounts created after threshold date")
        
        with col3:
            st.metric("✅ Legitimate Accounts", legitimate_count, help="Accounts created before threshold date")
        
        with col4:
            st.metric("❓ Unknown", unknown_count, help="Accounts with unavailable creation dates")
        
        # Detailed spam analysis
        if spam_count > 0:
            with st.expander(f"🔍 View {spam_count} Flagged Accounts", expanded=False):
                spam_df = pd.DataFrame(spam_accounts)
                spam_display_df = spam_df[['Username', 'Profile URL', 'Reactions', 'Reaction Count', 'Profile Creation Date', 'First Reaction Date']].copy()
                spam_display_df = spam_display_df.sort_values('Profile Creation Date', ascending=False)
                
                # Highlight very recent accounts (last 7 days)
                recent_threshold = datetime.now() - pd.Timedelta(days=7)
                st.markdown("**🔥 Very Recent Accounts (Last 7 days):**")
                
                very_recent = []
                for _, user in spam_display_df.iterrows():
                    try:
                        # Use the date-only field for comparison
                        creation_date_str = user['Profile Creation Date']
                        if creation_date_str not in ['N/A', 'Rate Limited']:
                            # Extract just the date part for comparison
                            creation_date = datetime.strptime(creation_date_str.split(' ')[0], '%Y-%m-%d')
                            if creation_date >= recent_threshold:
                                very_recent.append(user)
                    except:
                        pass
                
                if very_recent:
                    recent_df = pd.DataFrame(very_recent)
                    # Make usernames clickable for very recent accounts
                    recent_df['Username'] = recent_df.apply(
                        lambda row: create_clickable_username(row['Username'], row['Profile URL']), 
                        axis=1
                    )
                    recent_df = recent_df.drop('Profile URL', axis=1)
                    st.markdown(
                        recent_df.to_html(escape=False, index=False),
                        unsafe_allow_html=True
                    )
                else:
                    st.info("No accounts created in the last 7 days")
                
                st.markdown("**All Flagged Accounts:**")
                # Make usernames clickable for all flagged accounts
                spam_display_df['Username'] = spam_display_df.apply(
                    lambda row: create_clickable_username(row['Username'], row['Profile URL']), 
                    axis=1
                )
                spam_display_df = spam_display_df.drop('Profile URL', axis=1)
                st.markdown(
                    spam_display_df.to_html(escape=False, index=False),
                    unsafe_allow_html=True
                )
        
        # Display results
        st.success(f"Found {len(reactions)} unique users with reactions!")
        
        # Calculate total reactions
        total_reactions = sum(user['Reaction Count'] for user in reactions)
        
        # Create DataFrame
        df = pd.DataFrame(reactions)
        
        # Display summary statistics
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Total Reactions", total_reactions)
        with col2:
            st.metric("Unique Users", len(reactions))
        
        # Reaction distribution chart
        st.subheader("Reaction Distribution")
        
        # Count all individual reactions for the chart
        all_reaction_types = []
        for user in reactions:
            user_reactions = user['Reactions'].split()
            all_reaction_types.extend(user_reactions)
        
        if all_reaction_types:
            reaction_counts = pd.Series(all_reaction_types).value_counts()
            st.bar_chart(reaction_counts)
        
        # Main table with sorting
        st.subheader("All Users with Reactions")
        
        # Add sorting options
        col1, col2 = st.columns(2)
        with col1:
            sort_by = st.selectbox(
                "Sort by:",
                options=["Reaction Count", "First Reaction Date", "Profile Creation Date", "Username"],
                index=0,
                help="Choose how to sort the table",
                key="sort_by"
            )
        with col2:
            sort_order = st.selectbox(
                "Sort order:",
                options=["Descending", "Ascending"],
                index=0,
                help="Choose sort direction",
                key="sort_order"
            )
        
        # Create a copy of the DataFrame for display
        display_df = df.copy()
        
        # Convert Profile Creation Date to datetime for proper sorting (handle special cases)
        def convert_date_for_sorting(date_str):
            if date_str in ['N/A', 'Rate Limited']:
                return pd.Timestamp.min if sort_order == "Ascending" else pd.Timestamp.max
            try:
                return pd.to_datetime(date_str)
            except:
                return pd.Timestamp.min if sort_order == "Ascending" else pd.Timestamp.max
        
        # Apply sorting based on selection
        ascending = sort_order == "Ascending"
        
        if sort_by == "Reaction Count":
            display_df = display_df.sort_values('Reaction Count', ascending=ascending)
        elif sort_by == "First Reaction Date":
            display_df['First Reaction Date Temp'] = pd.to_datetime(display_df['First Reaction Date'])
            display_df = display_df.sort_values('First Reaction Date Temp', ascending=ascending)
            display_df = display_df.drop('First Reaction Date Temp', axis=1)
        elif sort_by == "Profile Creation Date":
            display_df['Profile Creation Date Temp'] = display_df['Profile Creation Date'].apply(convert_date_for_sorting)
            display_df = display_df.sort_values('Profile Creation Date Temp', ascending=ascending)
            display_df = display_df.drop('Profile Creation Date Temp', axis=1)
        elif sort_by == "Username":
            display_df = display_df.sort_values('Username', ascending=ascending)
        
        # Make usernames clickable in HTML
        display_df['Username'] = display_df.apply(
            lambda row: create_clickable_username(row['Username'], row['Profile URL']), 
            axis=1
        )
        
        # Remove the internal columns that aren't needed for display
        display_df = display_df.drop(['Profile URL', 'Profile Creation Date (Date Only)'], axis=1)
        
        # Display sorting information
        st.info(f"Table sorted by **{sort_by}** in **{sort_order.lower()}** order")
        
        # Display the table with HTML rendering for clickable links
        st.markdown(
            display_df.to_html(escape=False, index=False),
            unsafe_allow_html=True
        )
        
        # Download option
        csv = df.to_csv(index=False)
        st.download_button(
            label="Download CSV",
            data=csv,
            file_name=f"pr_reactions_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv"
        )

if __name__ == "__main__":
    main()
# GitHub PR Reactions Dashboard

A Streamlit dashboard to analyze GitHub Pull Request reactions and detect potential spam accounts.


https://github.com/user-attachments/assets/9e801c76-b90f-4de7-ad10-751cbecf0adf


## Setup

1. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure GitHub token**
   - Create a `.env` file in the project root
   - Add your GitHub token:
   ```
   GITHUB_TOKEN=your_github_token_here
   ```

3. **Run the dashboard**
   ```bash
   streamlit run main.py
   ```

4. **Open your browser**
   - Navigate to `http://localhost:8501`
   - Enter a GitHub PR URL to analyze reactions

## Usage

Enter a GitHub Pull Request URL (e.g., `https://github.com/owner/repo/pull/123`) and click "Analyze Reactions" to view reaction data and spam detection analysis.

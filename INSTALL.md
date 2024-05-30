# INSTALL

## 1. If install with Docker

1. **Clone the Repository**
   ```bash
   git clone https://github.com/yinan-c/rssbrew.git
   cd rssbrew
   ```
2. **Environment Variables**
   
   Copy the `.env.example` file to create a `.env` file. Modify the `.env` file to set necessary environment variables such as `OPENAI_API_KEY`, `SECRET_KEY`, and `DEPLOYMENT_URL`.
   
   ```bash
   cp .env.example .env
   # Edit .env to include necessary environment variables
   ```

3. **Build and Run the Docker Container**
   ```bash
   docker compose build
   docker compose up -d
   ```

## 2. If install without Docker

The same step 1 and 2 as the Docker installation above.

3. **Install Dependencies**
    ```bash
    pip install -r requirements.txt
    ```

4. **Initialize the App and run the server**
    ```bash
    python manage.py init_server
    python manage.py runserver
    ```

5. **Set up CRON Jobs**

To automate feed updates and digest generation, add the following entries to your crontab:

```bash
crontab -e
```

Add the following lines to schedule the tasks:

```bash
# Update feeds every hour
0 * * * * python3 manage.py update_feeds >> logs/cron.log 2>&1

# Generate digest daily at 6 AM
0 6 * * * python3 manage.py generate_digest >> logs/cron.log 2>&1
```

## Access the Application
After starting the server, you can access the application via http://localhost:8000/.

The default account credentials are:
- Username: `admin`
- Password: `changeme`

It is recommended to change the default password after your first login for security reasons. You can configure your RSS feeds, set filters, and adjust other settings from there.

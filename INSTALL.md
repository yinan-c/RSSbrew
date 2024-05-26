# INSTALL

## 1. with Docker

1. **Clone the Repository**
   ```bash
   git clone https://github.com/yinan-c/rssbrew.git
   cd rssbrew
   ```
2. **Environment Variables**
   
   Set environment variables such as `OPENAI_API_KEY`, `SECRET_KEY`, `DEPLOYMENT_URL` in `.env`.

   You can use the provided `.env.example` file as a template.

3. **Build and Run the Docker Container**
   ```bash
   docker compose build
   docker compose up -d
   ```

## 2. without Docker

The same step 1 and 2 as above.

3. **Install Dependencies**
    ```bash
    pip install -r requirements.txt
    ```

4. **Initialize the App and run the server**
    ```bash
    python manage.py init_server
    python manage.py runserver
    ```
## Access the Application
   
The application should be running at `http://localhost:8000/`.

The default username is `admin` and the password is `changeme`.

You can change the password after logging in. Configure your RSS feeds, filters, and settings from there.

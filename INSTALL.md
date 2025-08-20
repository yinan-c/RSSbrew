# INSTALL

1. **Download Docker Compose and .env.example**

```bash
wget https://raw.githubusercontent.com/yinan-c/rssbrew/main/docker-compose.yml
wget https://raw.githubusercontent.com/yinan-c/rssbrew/main/.env.example
```

2. **Modify Environment Variables**

   Copy the `.env.example` file to create a `.env` file. Modify the `.env` file to set necessary environment variables such as `OPENAI_API_KEY`, `SECRET_KEY`, and `DEPLOYMENT_URL`.

   ```bash
   cp .env.example .env
   # Edit .env to include necessary environment variables
   ```
   Modify `docker-compose.yml` as needed (e.g. ports, volumes, etc.)

3. **Start the server**

```bash
docker compose up -d
```

## Access the Application
After starting the server, you can access the application via http://localhost:8000/.

The default account credentials are:
- Username: `admin`
- Password: `changeme`

It is recommended to change the default password after your first login for security reasons. You can configure your RSS feeds, set filters, and adjust other settings from there.

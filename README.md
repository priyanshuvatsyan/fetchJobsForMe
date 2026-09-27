# fetchJobsForMe

Fetch jobs from public job-board APIs and print them in the terminal.

Run the commands below from the project folder. Python 3.10 or newer is enough. There are no extra packages to install.

## Fetch jobs

Every portal, up to 5 jobs each:

```powershell
python backend/Server/server.py --source all --query engineer --limit 5 --no-open
```

`--source` defaults to `all`, so this is the same search:

```powershell
python backend/Server/server.py --query engineer --limit 5 --no-open
```

One portal:

```powershell
python backend/Server/server.py --source arbeitnow --query automation --limit 5
```

Portals: `greenhouse`, `lever`, `ashby`, `remotive`, `remoteok`, `arbeitnow`, `adzuna`, `linkedin`.

```powershell
python backend/Server/server.py --list
```

`--limit` is the number of jobs per portal. `--query` matches the title, company, or location. `--where` matches a city or location. `--no-open` prints the LinkedIn search link without opening the browser.

Each job is printed as JSON with company, role, experience, skill, salary, added on, location, and link. With `--source all`, each record also includes `portal`.

## One company or a few companies

Greenhouse, Lever, and Ashby search the company list in `backend/connectors/companies.py`. To search only some of those companies, pass their board tokens with `--boards`:

```powershell
python backend/Server/server.py --source greenhouse --boards discord --query engineer --limit 5
```

```powershell
python backend/Server/server.py --source all --boards discord,cloudflare,spotify --query engineer --limit 5 --no-open
```

`--boards` applies to Greenhouse, Lever, and Ashby. A token that is not on that portal is skipped. Remotive, RemoteOK, and Arbeitnow do not use company tokens.

## Sort

`--sort` accepts `salary`, `date` (added on), and `exp` (experience). Separate keys with commas.

| Command | Order |
|---|---|
| `--sort salary` | Highest pay first |
| `--sort date` | Newest added on first |
| `--sort exp` | Lowest experience first |
| `--sort salary_asc` | Lowest pay first |
| `--sort date_asc` | Oldest added on first |
| `--sort exp_desc` | Highest experience first |
| `--sort salary_asc,date_asc` | Lowest pay first, then oldest date |

Jobs with a blank salary, date, or experience stay at the end.

```powershell
python backend/Server/server.py --source all --query automation --limit 5 --sort salary --no-open
```

```powershell
python backend/Server/server.py --source arbeitnow --query automation --limit 5 --sort exp_desc
```

## Adzuna

Adzuna is skipped until both keys are set. Create them at [developer.adzuna.com](https://developer.adzuna.com/).

```powershell
$env:ADZUNA_APP_ID = "your-app-id"
$env:ADZUNA_APP_KEY = "your-app-key"
python backend/Server/server.py --source adzuna --query engineer --where Bengaluru --country in
```

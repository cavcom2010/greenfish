# Multi-Client Setup Guide

This guide explains how to use the restaurant platform codebase for multiple clients without multi-tenancy complexity.

## Overview

Each client gets their **own isolated instance** with:
- Separate Git repository
- Separate database
- Separate deployment
- Custom branding/configuration

## Architecture

```
Base Template (restaurant-platform)
    ├── Your private GitHub repo
    ├── Never deployed directly
    └── Source of truth for features

Client A (marios-italian)
    ├── Clone of base
    ├── Own GitHub repo
    ├── Own domain & database
    └── Custom branding

Client B (sakura-sushi)
    ├── Clone of base
    ├── Own GitHub repo
    ├── Own domain & database
    └── Custom branding
```

## Setting Up a New Client

### Step 1: Clone the Base Template

```bash
# Clone your base template
git clone https://github.com/yourname/restaurant-platform.git marios-italian
cd marios-italian
```

### Step 2: Change the Git Remote

```bash
# Remove the base template remote
git remote remove origin

# Add the client's own remote
git remote add origin https://github.com/yourname/marios-italian.git

# Push to client's repo
git push -u origin main
```

### Step 3: Configure the Client's Instance

Edit `.env`:
```bash
DJANGO_SECRET_KEY=client-specific-secret-key
DJANGO_ALLOWED_HOSTS=mariositalian.com,www.mariositalian.com
DATABASE_URL=postgres://user:pass@localhost:5432/marios_db
SHOP_NAME=Mario's Italian Kitchen
# ... other client-specific settings
```

### Step 4: Customize (Optional)

**Easy customization (via Admin Panel):**
- Shop name, address, phone
- Logo, favicon
- Opening hours
- Menu items
- Theme color

**Advanced customization (template edits):**
```bash
# Edit templates for client-specific branding
vim templates/core/home.html
vim templates/base.html
vim static/css/custom.css
```

### Step 5: Deploy

```bash
# Deploy to client's server
./deploy/production/deploy.sh
```

## Keeping Clients Updated

When you add features to the base template, update all clients:

### One-Time Setup (Per Client)

```bash
cd marios-italian

# Add base template as "upstream" remote
git remote add upstream https://github.com/yourname/restaurant-platform.git
```

### Pulling Updates from Base

```bash
cd marios-italian

# Fetch latest changes from base
git fetch upstream

# Merge into client's branch
git merge upstream/main

# Handle any merge conflicts
# (if you customized templates, you may need to resolve conflicts)

# Push to client's repo
git push origin main

# Deploy
./deploy/production/deploy.sh
```

## What Stays The Same

All clients share identical:
- Django apps (orders, payments, loyalty, etc.)
- Database models
- Business logic
- API endpoints
- Admin panel
- Security updates

## What Changes Per Client

Each client has their own:
- **Database** - Completely isolated
- **SiteSettings** - Shop name, contact info, hours
- **Menu Items** - Food categories, prices
- **Theme** - Colors, logos (via CSS variables)
- **Domain** - mariositalian.com, sakurasushi.com
- **Templates** - If customized

## Git Workflow Summary

### Your Base Template
```bash
cd restaurant-platform
# Develop new features
git add .
git commit -m "Add delivery tracking feature"
git push origin main
```

### Each Client
```bash
cd marios-italian

# Pull latest from base
git fetch upstream
git merge upstream/main

# Resolve any conflicts
git push origin main

# Deploy
./deploy/production/deploy.sh
```

## Directory Structure Example

```
~/projects/
├── restaurant-platform/          # Your base template
│   ├── .git/config → origin: yourname/restaurant-platform
│   └── (never deployed)
│
├── marios-italian/               # Client A
│   ├── .git/config → origin: yourname/marios-italian
│   ├── .env (Mario's settings)
│   └── deployed to: mariositalian.com
│
├── sakura-sushi/                 # Client B
│   ├── .git/config → origin: yourname/sakura-sushi
│   ├── .env (Sakura's settings)
│   └── deployed to: sakurasushi.com
│
└── burger-barn/                  # Client C
    ├── .git/config → origin: yourname/burger-barn
    ├── .env (Burger Barn's settings)
    └── deployed to: burgerbarn.com
```

## Common Questions

### Q: Do clients share the same Git remote?
**A:** No. Each client has their own remote repository.

### Q: Can clients see each other's code?
**A:** No. Each client's repository is separate and private.

### Q: What if I customized templates for Client A?
**A:** When merging from base, you'll resolve conflicts. Keep client's customizations while adding new features.

### Q: Can I push Client A's changes back to the base?
**A:** Yes, if the changes are generic (not client-specific). Cherry-pick or manually copy changes.

### Q: What about security updates?
**A:** Update the base template, then merge into all client repos and redeploy.

### Q: Can clients customize their own templates?
**A:** Yes. They have full access to their repo and can modify templates freely.

## Best Practices

1. **Keep base template clean** - No hardcoded client-specific code
2. **Use SiteSettings** - Configure as much as possible via admin panel
3. **Document customizations** - Note what you changed per client
4. **Test before deploying** - Run tests after merging updates
5. **Use branches** - `main` for stable, `develop` for new features

## Quick Reference

```bash
# New client setup
git clone <base> <client>
cd <client>
git remote remove origin
git remote add origin <client-repo>
git push -u origin main

# Update client from base
git remote add upstream <base-repo>  # one-time
git fetch upstream
git merge upstream/main
git push origin main
```

## Need Help?

- See [DEPLOYMENT.md](DEPLOYMENT.md) for deployment details
- See [ARCHITECTURE.md](ARCHITECTURE.md) for codebase structure
- Check [ADMIN_GUIDE.md](ADMIN_GUIDE.md) for configuration

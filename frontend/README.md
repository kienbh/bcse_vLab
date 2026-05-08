# Frontend — VJU Hardware Lab Portal

Next.js 14 (App Router) + TypeScript + Tailwind. Auth via NextAuth (M1) hitting the
backend OIDC callback.

## Local dev

```bash
npm install
cp ../.env.example ../.env   # set NEXT_PUBLIC_API_URL=http://localhost:8000/api
npm run dev                  # → http://localhost:3000
```

## Build

```bash
npm run build && npm start
```

## Quality gates

```bash
npm run lint
npm run typecheck
npm run format:check
npm test
```

## Layout

```
src/
├── app/                  # App Router pages + layouts
│   ├── layout.tsx
│   ├── page.tsx          # M0 landing page
│   ├── globals.css
│   └── api/health/...    # internal health endpoint
├── components/           # shadcn-style components (M2+)
└── lib/                  # api client, auth helpers, utils
```

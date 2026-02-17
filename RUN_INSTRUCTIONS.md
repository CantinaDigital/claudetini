# How to Run Claudetini

## ✅ Fixed Import Error

The import error has been fixed. I added the missing `is_git_repo()` function to `src/core/git_utils.py`.

---

## 🚀 Running the Application

### Option 1: Full Tauri App (Recommended)

```bash
cd app
npm run tauri:dev
```

This starts:
- ✅ Backend (Python FastAPI on port 9876)
- ✅ Frontend (Vite dev server on port 1420)
- ✅ Tauri desktop app window

**First time running?** The Tauri build may take 2-3 minutes.

---

### Option 2: Backend + Frontend Separately (For Debugging)

**Terminal 1 - Backend:**
```bash
cd app
npm run backend
```

**Terminal 2 - Frontend:**
```bash
cd app
npm run dev
```

Then open http://localhost:5173 in your browser.

---

## 🧪 Testing the New Features

### 1. Test Readiness Scanner (Backend Only)

```bash
# Start backend
cd app && npm run backend

# In another terminal, test the API
curl -X POST http://127.0.0.1:9876/api/readiness/scan \
  -H "Content-Type: application/json" \
  -d '{"project_path": "/path/to/claudetini"}'
```

**Expected**: JSON response with score, checks, critical_issues, warnings

### 2. Test Bootstrap Cost Estimate

```bash
curl -X POST http://127.0.0.1:9876/api/bootstrap/estimate \
  -H "Content-Type: application/json" \
  -d '{"project_path": "/path/to/claudetini"}'
```

**Expected**: JSON with total_tokens, cost_usd, steps

### 3. Test Full GUI Flow

1. **Start the app**: `npm run tauri:dev`
2. **App opens to Project Picker**
   - Should see "Add Project" button
3. **Click "Add Project"**
   - Browse to a test project folder
   - Select it
4. **Readiness scan runs automatically**
   - Should see loading spinner
   - Then scorecard appears with circular score ring
5. **Check the scorecard**
   - Score 0-100 with color coding
   - Critical issues in red
   - Warnings in yellow
   - Detailed checks expandable
6. **Click "Bootstrap Missing Items"**
   - Cost estimate screen appears
   - Shows ~$0.30-0.40 cost
   - Checkboxes for skip options
7. **Click "Start Bootstrap"**
   - Progress screen with circular ring
   - Live status messages
   - Activity log scrolling
   - Wait 3-8 minutes
8. **Bootstrap completes**
   - Green checkmark
   - "Continue to Dashboard" button
9. **Click "Continue"**
   - Dashboard loads (existing Claudetini interface)

---

## 🐛 Common Issues

### "Backend not connected"

**Problem**: Frontend can't reach backend on port 9876

**Solution**:
```bash
# Check if backend is running
lsof -i :9876

# If not, start it
cd app && npm run backend
```

### "Module not found" errors

**Problem**: Python dependencies missing

**Solution**:
```bash
# Install dependencies
cd app/python-sidecar
pip install -e .

# Or use the root pyproject.toml
cd /path/to/claudetini
pip install -e .
```

### Bootstrap hangs or times out

**Problem**: Claude CLI not responding

**Solution**:
- Check Claude CLI is installed: `claude --version`
- Check Claude CLI is authenticated: `claude --help`
- Check internet connection
- Try with a smaller test project first

### Frontend TypeScript errors

**Problem**: Type mismatches in new components

**Solution**:
```bash
cd app
npm run type-check
```

Fix any reported type errors.

---

## 📊 What Should Work

### ✅ Backend Endpoints

- `POST /api/readiness/scan` - Readiness scanner
- `GET /api/readiness/score/{path}` - Quick score check
- `POST /api/bootstrap/estimate` - Cost estimate
- `POST /api/bootstrap/start` - Start bootstrap
- `GET /api/bootstrap/stream/{id}` - SSE progress stream
- `GET /api/bootstrap/status/{id}` - Status polling
- `GET /api/bootstrap/result/{id}` - Final result

### ✅ Frontend Screens

- **Project Picker** - Select/browse projects
- **Scorecard View** - Visual readiness score
- **Bootstrap Wizard** - Cost estimate + progress
- **Dashboard** - Existing app (unchanged)

### ✅ State Machine

- `picker` → `scorecard` → `bootstrap` → `dashboard`
- Automatic transitions
- Smooth animations

---

## 🎯 Test Checklist

### Backend Tests
- [ ] Readiness scan returns valid score (0-100)
- [ ] All 12 checks execute
- [ ] Remediation prompts provided for failures
- [ ] Cost estimate returns reasonable values
- [ ] Bootstrap start returns session_id
- [ ] SSE stream sends progress events

### Frontend Tests
- [ ] Project picker loads
- [ ] Can select a project
- [ ] Readiness scan runs automatically
- [ ] Scorecard displays with circular ring
- [ ] Score color matches value (green/yellow/orange/red)
- [ ] Critical issues and warnings display
- [ ] Bootstrap wizard shows cost estimate
- [ ] Progress view animates smoothly
- [ ] SSE updates work in real-time
- [ ] Completion screen appears
- [ ] Can navigate to dashboard

### Integration Tests
- [ ] Full flow: picker → scorecard → bootstrap → dashboard
- [ ] "Skip for Now" bypasses bootstrap
- [ ] Refresh button re-scans readiness
- [ ] Bootstrap creates expected files
- [ ] Dashboard loads with new project

---

## 🚑 Emergency Rollback

If something is completely broken:

```bash
cd /path/to/claudetini

# Revert router changes
git checkout app/src/main.tsx

# Use old App directly
# Edit main.tsx to import App instead of AppRouter
```

---

## 📝 Development Notes

### File Locations

**Backend**:
- `src/core/readiness.py` - Readiness scanner
- `app/python-sidecar/sidecar/api/routes/readiness.py` - API
- `app/python-sidecar/sidecar/api/routes/bootstrap.py` - API

**Frontend**:
- `app/src/AppRouter.tsx` - Screen router
- `app/src/components/scorecard/` - Scorecard components
- `app/src/components/bootstrap/` - Bootstrap components
- `app/src/store/index.ts` - State management

### State Flow

```typescript
// User selects project
store.currentProject = project
store.setScreen('scorecard')

// Auto-scan readiness
store.scanReadiness(project.path)
// → readinessScore, readinessReport updated

// User clicks "Bootstrap"
store.setScreen('bootstrap')
store.startBootstrap(project.path)
// → bootstrapSessionId set

// Progress updates via SSE
EventSource('/api/bootstrap/stream/{id}')
// → Progress bar animates

// Completion
store.completeBootstrap()
// → currentScreen = 'dashboard'
```

---

## 🎉 Success!

If you see:
1. ✅ Project Picker loads
2. ✅ Readiness score appears
3. ✅ Bootstrap wizard works
4. ✅ Progress updates in real-time
5. ✅ Dashboard loads after completion

**You're ready for beta testing!** 🚀

---

**Created**: 2026-02-14
**Status**: Ready to run
**Next**: Test the full flow end-to-end

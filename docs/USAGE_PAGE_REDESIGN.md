# Usage Page Redesign Proposal

## Overview
Redesign the usage page to focus on **evolution runs** as the primary metric, removing all references to tokens and costs. The page should help users understand their playbook activity and evolution performance.

---

## Page Layout

### 1. Summary Cards (Top Row)
Four key metrics displayed as cards:

```
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│  📊 Total       │  │  ✅ Successful  │  │  ❌ Failed      │  │  📈 Success     │
│  Evolutions     │  │  Evolutions     │  │  Evolutions     │  │  Rate           │
│                 │  │                 │  │                 │  │                 │
│  24             │  │  22             │  │  2              │  │  92%            │
└─────────────────┘  └─────────────────┘  └─────────────────┘  └─────────────────┘
```

**Metrics:**
- **Total Evolutions**: Total evolution runs in the period
- **Successful**: Evolutions with status `COMPLETED`
- **Failed**: Evolutions with status `FAILED`
- **Success Rate**: Percentage of successful evolutions

---

### 2. Evolution Activity Chart (Main Section)

**Daily Evolution Runs** - Stacked bar chart showing evolution activity over time

```
┌─────────────────────────────────────────────────────────────────┐
│ Evolution Activity                            Last 30 days      │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   ▆                                                             │
│   █         ▆                                                   │
│   █   ▃     █       ▃                                           │
│   █   █  ▃  █   ▃   █                                           │
│   █   █  █  █   █   █                                           │
│  ─┴───┴──┴──┴───┴───┴──────────────────────────────────────── │
│  Mon Tue Wed Thu Fri Sat Sun ...                                │
│                                                                 │
│  Legend: █ Completed  ░ Failed  ▒ Running                       │
└─────────────────────────────────────────────────────────────────┘
```

**Features:**
- Stacked bars showing completed (green), failed (red), and running (yellow)
- Hover tooltip showing exact counts per day
- Last 14 days displayed by default
- Option to view 7/14/30/90 days

---

### 3. Playbook Activity (Right Sidebar)

**Evolution Runs by Playbook** - List showing which playbooks are most active

```
┌─────────────────────────────────────────────────────────────────┐
│ Playbook Activity                                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  📘 Customer Support Playbook                                   │
│     12 evolutions · 92% success                                 │
│     Last run: 2 hours ago                                       │
│                                                                 │
│  📘 Sales Qualification                                         │
│     8 evolutions · 100% success                                 │
│     Last run: 1 day ago                                         │
│                                                                 │
│  📘 Bug Triage Process                                          │
│     4 evolutions · 75% success                                  │
│     Last run: 3 days ago                                        │
│                                                                 │
│  [View All Playbooks →]                                         │
└─────────────────────────────────────────────────────────────────┘
```

**Features:**
- Clickable playbook names (navigate to playbook detail)
- Evolution count and success rate
- Last evolution timestamp
- Top 5 playbooks by activity

---

### 4. Recent Activity Timeline (Optional Bottom Section)

**Recent Evolution Runs** - Timeline of recent evolution activity

```
┌─────────────────────────────────────────────────────────────────┐
│ Recent Activity                                                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ✅  Customer Support Playbook evolved successfully             │
│      2 hours ago · 3 outcomes processed · v1.2 → v1.3          │
│                                                                 │
│  ✅  Sales Qualification evolved successfully                   │
│      5 hours ago · 5 outcomes processed · v2.1 → v2.2          │
│                                                                 │
│  ❌  Bug Triage Process evolution failed                        │
│      1 day ago · Error: Invalid outcome format                 │
│                                                                 │
│  ✅  Customer Support Playbook evolved successfully             │
│      2 days ago · 2 outcomes processed · v1.1 → v1.2           │
│                                                                 │
│  [View All Evolution History →]                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Features:**
- Status icon (✅ completed, ❌ failed, ⏳ running, ⏸ queued)
- Playbook name (clickable)
- Time ago
- Outcomes processed count
- Version progression (from_version → to_version)
- Error message for failed jobs
- Last 10 evolution runs shown

---

## Empty States

### No Evolution Runs Yet

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│                          📊                                     │
│                                                                 │
│              No Evolution Runs Yet                              │
│                                                                 │
│     Your playbooks haven't been evolved yet. Add outcomes       │
│     to your playbooks and click "Evolve" to see activity.       │
│                                                                 │
│               [Go to Playbooks →]                               │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Time Period Selector

Add a dropdown in the page header to filter by time period:

```
Usage Activity  [Last 30 days ▼]
```

**Options:**
- Last 7 days
- Last 14 days
- Last 30 days (default)
- Last 90 days
- All time

---

## Technical Requirements

### New Backend API Endpoints

#### 1. **GET /evolutions/summary**
Returns aggregated evolution statistics for the user.

**Response:**
```json
{
  "start_date": "2024-01-01T00:00:00Z",
  "end_date": "2024-01-31T23:59:59Z",
  "total_evolutions": 24,
  "completed_evolutions": 22,
  "failed_evolutions": 2,
  "running_evolutions": 0,
  "queued_evolutions": 0,
  "success_rate": 0.92,
  "total_outcomes_processed": 67
}
```

#### 2. **GET /evolutions/daily**
Returns daily evolution breakdown.

**Query Parameters:**
- `start_date` (optional): Start date (defaults to 30 days ago)
- `end_date` (optional): End date (defaults to now)

**Response:**
```json
[
  {
    "date": "2024-01-22",
    "total_evolutions": 5,
    "completed": 4,
    "failed": 1,
    "running": 0,
    "queued": 0
  },
  ...
]
```

#### 3. **GET /evolutions/by-playbook**
Returns evolution statistics grouped by playbook.

**Query Parameters:**
- `start_date` (optional)
- `end_date` (optional)
- `limit` (optional): Number of playbooks to return (default: 10)

**Response:**
```json
[
  {
    "playbook_id": "uuid",
    "playbook_name": "Customer Support Playbook",
    "total_evolutions": 12,
    "completed": 11,
    "failed": 1,
    "success_rate": 0.92,
    "last_evolution_at": "2024-01-22T10:30:00Z"
  },
  ...
]
```

#### 4. **GET /evolutions/recent**
Returns recent evolution runs across all playbooks.

**Query Parameters:**
- `limit` (optional): Number of runs to return (default: 10)

**Response:**
```json
[
  {
    "id": "uuid",
    "playbook_id": "uuid",
    "playbook_name": "Customer Support Playbook",
    "status": "completed",
    "outcomes_processed": 3,
    "from_version_number": 1,
    "to_version_number": 2,
    "started_at": "2024-01-22T10:00:00Z",
    "completed_at": "2024-01-22T10:05:00Z",
    "error_message": null
  },
  ...
]
```

---

## Frontend Components

### File Structure
```
web/src/pages/Usage/
├── Usage.tsx                    # Main page component
├── Usage.module.css             # Styles
├── components/
│   ├── EvolutionSummaryCard.tsx # Summary metric card
│   ├── EvolutionChart.tsx       # Stacked bar chart
│   ├── PlaybookActivity.tsx     # Playbook list
│   ├── RecentActivity.tsx       # Activity timeline
│   └── EmptyState.tsx           # No data state
```

### New TypeScript Interfaces

```typescript
export interface EvolutionSummary {
  start_date: string;
  end_date: string;
  total_evolutions: number;
  completed_evolutions: number;
  failed_evolutions: number;
  running_evolutions: number;
  queued_evolutions: number;
  success_rate: number;
  total_outcomes_processed: number;
}

export interface DailyEvolution {
  date: string;
  total_evolutions: number;
  completed: number;
  failed: number;
  running: number;
  queued: number;
}

export interface PlaybookEvolutionStats {
  playbook_id: string;
  playbook_name: string;
  total_evolutions: number;
  completed: number;
  failed: number;
  success_rate: number;
  last_evolution_at: string | null;
}

export interface RecentEvolution {
  id: string;
  playbook_id: string;
  playbook_name: string;
  status: 'queued' | 'running' | 'completed' | 'failed';
  outcomes_processed: number;
  from_version_number: number | null;
  to_version_number: number | null;
  started_at: string | null;
  completed_at: string | null;
  error_message: string | null;
}
```

---

## Design Rationale

### Why This Design?

1. **User-Focused Metrics**: Customers care about evolution runs, not tokens/costs
2. **Actionable Insights**: Users can see which playbooks are active and success rates
3. **Activity Monitoring**: Daily chart shows usage patterns and trends
4. **Quick Debugging**: Failed evolutions are prominently displayed with error messages
5. **Performance Tracking**: Success rate helps users understand playbook quality

### What's Removed?

- ❌ Token counts
- ❌ Cost information (USD)
- ❌ Prompt/completion token breakdown
- ❌ Any LLM-specific metrics

### What's Added?

- ✅ Evolution run counts
- ✅ Success/failure tracking
- ✅ Playbook-level activity
- ✅ Recent evolution timeline
- ✅ Success rate percentage

---

## Implementation Plan

### Phase 1: Backend (Estimated: 4-6 hours)
1. Create new API routes in `ace_platform/api/routes/evolutions.py`
2. Implement aggregation queries in `ace_platform/core/evolution_stats.py`
3. Add response models and validation
4. Write tests for new endpoints

### Phase 2: Frontend (Estimated: 6-8 hours)
1. Update TypeScript interfaces
2. Create new API client functions
3. Build new components (summary cards, chart, lists)
4. Update main Usage page to use new components
5. Add time period selector
6. Style with existing design system

### Phase 3: Testing & Polish (Estimated: 2-3 hours)
1. Test with empty state (new user)
2. Test with various data scenarios
3. Mobile responsive design
4. Loading states and error handling

**Total Estimate: 12-17 hours**

---

## Alternative Layouts

### Option A: Full-Width Chart
- Move playbook activity below the chart
- Wider chart for better data visualization
- Better for users with many evolutions per day

### Option B: Grid Layout
- 2x2 grid of equal-sized sections
- Summary cards at top
- Chart and playbook activity side-by-side
- Recent activity at bottom
- Better for balanced information density

### Option C: Dashboard-Style
- Multiple smaller widgets
- Draggable/rearrangeable sections
- More customization for power users
- More complex to implement

---

## Open Questions

1. **Time Range**: Should we show 14 days or 30 days by default in the chart?
2. **Playbook Limit**: Show top 5 or top 10 playbooks in the activity list?
3. **Recent Activity**: Include or skip this section in v1?
4. **Status Colors**:
   - Green for completed ✅
   - Red for failed ❌
   - Yellow for running ⏳
   - Gray for queued ⏸
5. **Navigation**: Should playbook names link to playbook detail or evolution history?

---

## Future Enhancements (v2)

- Export evolution data as CSV
- Email reports for failed evolutions
- Comparison view (this month vs last month)
- Evolution duration/performance metrics
- Filtering by playbook or status
- Search evolution history

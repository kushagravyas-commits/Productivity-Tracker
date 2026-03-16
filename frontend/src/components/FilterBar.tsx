import { FilterState } from '../pages/Logs'

interface FilterBarProps {
  apps: string[]
  categories: Array<'productive' | 'neutral' | 'distracting'>
  currentFilters: FilterState
  currentSort: { by: string; order: 'asc' | 'desc' }
  onFilterChange: (filters: Partial<FilterState>) => void
  onSortChange: (by: string, order: 'asc' | 'desc') => void
  onClearFilters: () => void
}

export default function FilterBar({
  apps,
  categories,
  currentFilters,
  currentSort,
  onFilterChange,
  onSortChange,
  onClearFilters,
}: FilterBarProps) {
  const handleCategoryToggle = (cat: 'productive' | 'neutral' | 'distracting') => {
    onFilterChange({
      category: currentFilters.category === cat ? null : cat,
    })
  }

  return (
    <div className="filter-bar">
      <div className="filter-group">
        <label htmlFor="app-filter">App</label>
        <select
          id="app-filter"
          value={currentFilters.appName || ''}
          onChange={(e) =>
            onFilterChange({
              appName: e.target.value ? e.target.value : null,
            })
          }
        >
          <option value="">All Apps</option>
          {apps.map((app) => (
            <option key={app} value={app}>
              {app}
            </option>
          ))}
        </select>
      </div>

      <div className="filter-group">
        <label>Category</label>
        <div className="category-toggles">
          {categories.map((cat) => (
            <button
              key={cat}
              className={`category-btn ${currentFilters.category === cat ? 'active' : ''}`}
              onClick={() => handleCategoryToggle(cat)}
            >
              {cat.charAt(0).toUpperCase() + cat.slice(1)}
            </button>
          ))}
        </div>
      </div>

      <div className="filter-group">
        <label htmlFor="search-filter">Search Title</label>
        <input
          id="search-filter"
          type="text"
          placeholder="Window title..."
          value={currentFilters.searchQuery}
          onChange={(e) =>
            onFilterChange({
              searchQuery: e.target.value,
            })
          }
        />
      </div>

      <div className="filter-group">
        <label htmlFor="sort-by">Sort By</label>
        <select
          id="sort-by"
          value={currentSort.by}
          onChange={(e) => onSortChange(e.target.value, currentSort.order)}
        >
          <option value="time">Time</option>
          <option value="duration">Duration</option>
          <option value="app">App Name</option>
        </select>
      </div>

      <div className="filter-group">
        <label>&nbsp;</label>
        <button
          className="sort-order-btn"
          onClick={() =>
            onSortChange(currentSort.by, currentSort.order === 'asc' ? 'desc' : 'asc')
          }
          title={`Sort ${currentSort.order === 'asc' ? 'descending' : 'ascending'}`}
        >
          {currentSort.order === 'asc' ? '↑ Asc' : '↓ Desc'}
        </button>
      </div>

      <button className="clear-filters-btn" onClick={onClearFilters}>
        Clear Filters
      </button>
    </div>
  )
}

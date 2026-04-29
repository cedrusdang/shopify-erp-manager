# Error Logging System Documentation

## Overview
The Shopify ERP application now includes a comprehensive error logging system that captures all errors, warnings, and informational messages to log files and the console.

## Log Files

Log files are stored in the `logs/` directory with the following naming convention:
- **Main Log**: `shopify_erp_YYYYMMDD.log` - All DEBUG and above level messages
- **Error Log**: `shopify_erp_errors_YYYYMMDD.log` - Only ERROR and CRITICAL level messages

## Log Levels

The application uses standard Python logging levels:
- **DEBUG** - Detailed diagnostic information (e.g., API calls, data processing)
- **INFO** - Informational messages (e.g., successful operations, startup events)
- **WARNING** - Warning messages (e.g., non-critical failures, degraded operations)
- **ERROR** - Error messages (e.g., failed API calls, file I/O errors)
- **CRITICAL** - Critical errors that may cause app failure

## Log Output Destinations

### Main Log File (`shopify_erp_YYYYMMDD.log`)
- **Level**: DEBUG and above
- **Format**: `YYYY-MM-DD HH:MM:SS | module_name | LEVEL    | function:line | message`
- **Size Limit**: 10 MB per file with automatic rotation (keeps 10 backup files)
- **Contents**: All application events, API interactions, and errors

### Error Log File (`shopify_erp_errors_YYYYMMDD.log`)
- **Level**: ERROR and CRITICAL
- **Format**: Same as main log with full stack traces
- **Size Limit**: 10 MB per file with automatic rotation
- **Contents**: Only error events with detailed traceback information

### Console Output
- **Level**: WARNING and above
- **Format**: `YYYY-MM-DD HH:MM:SS | LEVEL    | message`
- **Display**: Only critical warnings and errors (for user visibility)

## Logged Components

### Application Startup (`__main__.py`)
- Dependency checks
- Login window initialization
- Application initialization and startup messages
- Fatal errors with full stack traces

### API Operations (`api.py`)
- API connection attempts
- GraphQL request/response errors
- Token fetch operations
- HTTP errors and connection issues

### Main Application Window (`ui/app.py`)
- Token fetch requests
- Connection testing
- Auto-initialization attempts
- Connection success/failure events

### Download Operations (`ui/tab_download.py`)
- Download mode and parameters
- Product fetch progress
- Image download statistics
- Excel file creation and saving
- Backup operations
- Download completion statistics
- Download errors and exceptions

## Usage Example

When running the application:
```bash
python main.py
```

Log files will be automatically created in the `logs/` directory. To view logs:
```bash
# View main log (last 100 lines)
tail -100 logs/shopify_erp_20260429.log

# View error log (last 50 lines)
tail -50 logs/shopify_erp_errors_20260429.log

# View all errors from today
grep ERROR logs/shopify_erp_20260429.log
```

## Features

1. **Automatic Log Rotation**: Log files are automatically rotated when they exceed 10 MB
2. **Separate Error Tracking**: Errors are duplicated to both main and error-only logs
3. **Detailed Context**: Each log entry includes timestamp, module name, function name, and line number
4. **Stack Traces**: Full exception tracebacks are captured for debugging
5. **Console Suppression**: Console output is suppressed on Windows but logging continues to files
6. **Daily Rotation**: New log files are created each day based on the date in the filename

## Troubleshooting

If the application encounters an error:
1. Check the `logs/shopify_erp_YYYYMMDD.log` file for detailed information
2. Review the `logs/shopify_erp_errors_YYYYMMDD.log` for error summaries
3. Look for the most recent entry with an ERROR or CRITICAL level
4. Check the full stack trace for the root cause

## Example Log Entries

### Successful API Token Fetch
```
2026-04-29 16:58:46 | shopify_erp.api | INFO     | fetch_access_token:115 | Successfully fetched access token for oz-nails-wa.myshopify.com
```

### Download Started
```
2026-04-29 16:59:00 | shopify_erp.ui.tab_download | INFO | _start_download:335 | Download started - Mode: All Pages, Store: oz-nails-wa.myshopify.com
```

### Error Capture
```
2026-04-29 16:59:05 | shopify_erp.ui.tab_download | ERROR    | _start_download:461 | Download error: Connection timeout after 30 seconds
```

## Future Enhancements

- Real-time log viewer in the GUI
- Log file cleanup options
- Configurable log levels
- Email alerts for critical errors

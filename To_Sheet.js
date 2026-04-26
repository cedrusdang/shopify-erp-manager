function To_Sheet() {
  const sheet_name = SpreadsheetApp.getActive()
    .getSheetByName("Menu")
    .getRange("A2")
    .getValue()
    .toString()
    .trim();

  const ui = SpreadsheetApp.getUi();

  const confirm = ui.alert(
    "Import from Shopify?",
    "This will load ALL products from Shopify and overwrite existing data. Continue?",
    ui.ButtonSet.YES_NO
  );
  if (confirm !== ui.Button.YES) return;

  // 🔥 CLEAR IMMEDIATELY AFTER CONFIRMATION
  Clear();

  SpreadsheetApp.getActive().toast("Starting import...");

  const store = PropertiesService.getScriptProperties().getProperty("STORE_DOMAIN");
  const token = PropertiesService.getScriptProperties().getProperty("ACCESS_TOKEN");

  const sheet = SpreadsheetApp.getActive().getSheetByName(sheet_name);
  const lastCol = sheet.getLastColumn();
  const header = sheet.getRange(1, 1, 1, lastCol).getValues()[0];

  function getByPath(obj, path) {
    try {
      return path.split('.').reduce((o, k) => {
        if (/^\d+$/.test(k)) return o[parseInt(k, 10)];
        return o[k];
      }, obj) ?? "";
    } catch (e) {
      return "";
    }
  }

  const products = fetchAllProducts(store, token);
  const total = products.length;
  const batchSize = 200;

  SpreadsheetApp.getActive().toast(`Processing ${total} products in batches...`);

  let rowPointer = 2;

  for (let start = 0; start < total; start += batchSize) {
    const end = Math.min(start + batchSize, total);
    const batch = products.slice(start, end);

    SpreadsheetApp.getActive().toast(`Writing rows ${start} to ${end}...`);

    const rows = batch.map(p =>
      header.map(col => getByPath(p, col.trim()))
    );

    sheet.getRange(rowPointer, 1, rows.length, header.length).setValues(rows);
    rowPointer += rows.length;
  }

  ui.alert(`Import completed.\nProducts loaded: ${total}`);
}

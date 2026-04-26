function Clear() {
  const sheet_name = SpreadsheetApp.getActive().getSheetByName("Menu").getRange("A2").getValue()

  const ui = SpreadsheetApp.getUi();

  const confirm = ui.alert(
    "Clear Data?",
    "This will delete all rows except the header. Continue?",
    ui.ButtonSet.YES_NO
  );
  if (confirm !== ui.Button.YES) return;

  const sheet = SpreadsheetApp.getActive().getSheetByName(sheet_name);
  const lastRow = sheet.getLastRow();
  const lastCol = sheet.getLastColumn();

  const count = lastRow - 1;

  SpreadsheetApp.getActive().toast(`Clearing ${count} rows...`);

  if (count > 0) {
    sheet.getRange(2, 1, count, lastCol).clearContent();
  }

  ui.alert(`Clear completed.\nRows deleted: ${count}`);
}

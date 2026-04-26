function updateStatus(msg) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const menuSheet = ss.getSheetByName("Menu");
  if (!menuSheet) return;
  menuSheet.getRange("B4").setValue(msg);
}

function safeToast(msg, title, timeout) {
  try {
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    ss.toast(msg, title || "", timeout || 3);
  } catch (e) {
    // ignore in triggers
  }
}

// Helper: lấy value an toàn theo header
function getVal(row, header, key) {
  const idx = header.indexOf(key);
  return idx >= 0 ? row[idx] : "";
}

// Xoá trigger cũ để tránh spam
function clearTriggers() {
  ScriptApp.getProjectTriggers().forEach(t => {
    if (t.getHandlerFunction() === "To_Shopify_One") {
      ScriptApp.deleteTrigger(t);
    }
  });
}

function To_Shopify() {
  const ui = SpreadsheetApp.getUi();
  const confirm = ui.alert(
    "Export to Shopify?",
    "This will update products ONE BY ONE. Continue?",
    ui.ButtonSet.YES_NO
  );
  if (confirm !== ui.Button.YES) return;

  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const menuSheet = ss.getSheetByName("Menu");

  if (!menuSheet) {
    ui.alert("Menu sheet not found!");
    return;
  }

  const sheetName = menuSheet.getRange("A2").getValue().toString().trim();
  const sheet = ss.getSheetByName(sheetName);

  if (!sheet) {
    ui.alert(`Sheet "${sheetName}" not found`);
    return;
  }

  const lastRow = sheet.getLastRow();

  const props = PropertiesService.getScriptProperties();
  props.setProperty("EXPORT_SHEET", sheetName);
  props.setProperty("EXPORT_POINTER", "2");
  props.setProperty("EXPORT_LASTROW", lastRow.toString());
  props.setProperty("EXPORT_RETRIES", "0");
  props.setProperty("EXPORT_FAILS", "0");

  clearTriggers();

  updateStatus("Starting export...");
  safeToast("Starting export...");

  To_Shopify_One();
}

function To_Shopify_One() {
  const props = PropertiesService.getScriptProperties();

  const sheetName = props.getProperty("EXPORT_SHEET");
  const pointer = Number(props.getProperty("EXPORT_POINTER"));
  const lastRow = Number(props.getProperty("EXPORT_LASTROW"));

  const store = props.getProperty("STORE_DOMAIN");
  const token = props.getProperty("ACCESS_TOKEN");

  if (!store || !token) {
    updateStatus("Missing STORE_DOMAIN or ACCESS_TOKEN");
    return;
  }

  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = ss.getSheetByName(sheetName);

  if (!sheet) {
    updateStatus(`Sheet "${sheetName}" not found`);
    return;
  }

  const lastCol = sheet.getLastColumn();
  const header = sheet.getRange(1, 1, 1, lastCol).getValues()[0];

  // DONE
  if (pointer > lastRow) {
    const retries = props.getProperty("EXPORT_RETRIES");
    const fails = props.getProperty("EXPORT_FAILS");

    const doneMsg =
      `Export completed\nRows: ${lastRow - 1}\nRetries: ${retries}\nFailed: ${fails}`;

    updateStatus(doneMsg);
    safeToast("Export completed");
    clearTriggers();
    return;
  }

  const row = sheet.getRange(pointer, 1, 1, lastCol).getValues()[0];

  const productId = getVal(row, header, "id");

  if (!productId) {
    updateStatus(`Skip row ${pointer} (no ID)`);
    props.setProperty("EXPORT_POINTER", (pointer + 1).toString());
    scheduleNext();
    return;
  }

  updateStatus(`Updating ID ${productId} (row ${pointer})`);
  safeToast(`Updating ${productId}`);

  const payload = {
    product: {
      id: productId,
      title: getVal(row, header, "title"),
      body_html: getVal(row, header, "body_html"),
      vendor: getVal(row, header, "vendor"),
      product_type: getVal(row, header, "product_type"),
      tags: getVal(row, header, "tags")
    }
  };

  const url = `https://${store}/admin/api/2024-01/products/${productId}.json`;

  let attempt = 0;
  let success = false;

  while (!success && attempt < 5) {
    try {
      const res = UrlFetchApp.fetch(url, {
        method: "put",
        headers: {
          "X-Shopify-Access-Token": token,
          "Content-Type": "application/json"
        },
        payload: JSON.stringify(payload),
        muteHttpExceptions: true
      });

      const code = res.getResponseCode();
      const body = res.getContentText();

      let json = {};
      try {
        json = JSON.parse(body);
      } catch (e) {}

      if (code >= 200 && code < 300) {
        success = true;

      } else if (code === 429 || code >= 500) {
        attempt++;

        props.setProperty(
          "EXPORT_RETRIES",
          (Number(props.getProperty("EXPORT_RETRIES")) + 1).toString()
        );

        const err = json.errors
          ? JSON.stringify(json.errors)
          : body;

        updateStatus(`Retry ${attempt}/5 (${code})`);
        safeToast(`Retry ${attempt}`);

        Utilities.sleep(1000 * Math.pow(2, attempt));

      } else {
        const err = json.errors
          ? JSON.stringify(json.errors)
          : body;

        updateStatus(`Fail ID ${productId}: ${code}`);
        safeToast(`Fail ${productId}`);

        props.setProperty(
          "EXPORT_FAILS",
          (Number(props.getProperty("EXPORT_FAILS")) + 1).toString()
        );

        success = true;
      }

    } catch (e) {
      attempt++;

      props.setProperty(
        "EXPORT_RETRIES",
        (Number(props.getProperty("EXPORT_RETRIES")) + 1).toString()
      );

      updateStatus(`Exception retry ${attempt}`);
      safeToast(`Retry ${attempt}`);

      Utilities.sleep(1000 * Math.pow(2, attempt));
    }
  }

  props.setProperty("EXPORT_POINTER", (pointer + 1).toString());

  scheduleNext();
}

function scheduleNext() {
  clearTriggers();

  updateStatus("Next product...");
  safeToast("Next...");

  ScriptApp.newTrigger("To_Shopify_One")
    .timeBased()
    .after(2000)
    .create();
}
function Set_Product_Fields_As_Headers() {

  const sheet_name = SpreadsheetApp.getActive().getSheetByName("Menu").getRange("A2").getValue();
  const sheet = SpreadsheetApp.getActive().getSheetByName(sheet_name);

  const store = PropertiesService.getScriptProperties().getProperty("STORE_DOMAIN");
  const token = PropertiesService.getScriptProperties().getProperty("ACCESS_TOKEN");

  const productId = "9387070095595";

  const headers = {
    "X-Shopify-Access-Token": token,
    "Content-Type": "application/json"
  };

  // Fetch product
  const productRes = UrlFetchApp.fetch(
    `https://${store}/admin/api/2024-01/products/${productId}.json`,
    { method: "get", headers, muteHttpExceptions: true }
  );
  const product = JSON.parse(productRes.getContentText()).product;

  if (!product) {
    SpreadsheetApp.getUi().alert("Product not found or API error.");
    return;
  }

  // Fetch ALL product metafield definitions via GraphQL
  const gqlRes = UrlFetchApp.fetch(
    `https://${store}/admin/api/2024-01/graphql.json`,
    {
      method: "post",
      headers,
      payload: JSON.stringify({
        query: `{
          metafieldDefinitions(first: 250, ownerType: PRODUCT) {
            edges {
              node {
                namespace
                key
              }
            }
          }
        }`
      }),
      muteHttpExceptions: true
    }
  );

  const gqlData = JSON.parse(gqlRes.getContentText());
  const definitions = gqlData.data.metafieldDefinitions.edges.map(e => e.node);

  // Seed product.metafields from all definitions
  product.metafields = {};
  definitions.forEach(d => {
    if (!product.metafields[d.namespace]) product.metafields[d.namespace] = {};
    product.metafields[d.namespace][d.key] = "";
  });

  // Overwrite with actual values
  const metaRes = UrlFetchApp.fetch(
    `https://${store}/admin/api/2024-01/products/${productId}/metafields.json`,
    { method: "get", headers, muteHttpExceptions: true }
  );
  const metafields = JSON.parse(metaRes.getContentText()).metafields || [];
  metafields.forEach(m => {
    if (!product.metafields[m.namespace]) product.metafields[m.namespace] = {};
    product.metafields[m.namespace][m.key] = m.value;
  });

  // Fetch ALL variant metafield definitions via GraphQL
  const vGqlRes = UrlFetchApp.fetch(
    `https://${store}/admin/api/2024-01/graphql.json`,
    {
      method: "post",
      headers,
      payload: JSON.stringify({
        query: `{
          metafieldDefinitions(first: 250, ownerType: PRODUCTVARIANT) {
            edges {
              node {
                namespace
                key
              }
            }
          }
        }`
      }),
      muteHttpExceptions: true
    }
  );

  const vGqlData = JSON.parse(vGqlRes.getContentText());
  const vDefinitions = vGqlData.data.metafieldDefinitions.edges.map(e => e.node);

  // Seed + overwrite variant metafields
  if (product.variants && product.variants.length > 0) {
    product.variants.forEach((variant, i) => {
      product.variants[i].metafields = {};

      vDefinitions.forEach(d => {
        if (!product.variants[i].metafields[d.namespace]) product.variants[i].metafields[d.namespace] = {};
        product.variants[i].metafields[d.namespace][d.key] = "";
      });

      const vMetaRes = UrlFetchApp.fetch(
        `https://${store}/admin/api/2024-01/variants/${variant.id}/metafields.json`,
        { method: "get", headers, muteHttpExceptions: true }
      );
      const vMetafields = JSON.parse(vMetaRes.getContentText()).metafields || [];
      vMetafields.forEach(m => {
        if (!product.variants[i].metafields[m.namespace]) product.variants[i].metafields[m.namespace] = {};
        product.variants[i].metafields[m.namespace][m.key] = m.value;
      });
    });
  }

  // Flatten to dot-notation field paths only
  const fields = [];

  function flatten(obj, prefix) {
    prefix = prefix || "";
    for (const key in obj) {
      if (!obj.hasOwnProperty(key)) continue;
      const path = prefix ? prefix + "." + key : key;
      const value = obj[key];

      if (value === null || value === undefined) {
        fields.push(path);
      } else if (Array.isArray(value)) {
        if (value.length === 0) {
          fields.push(path);
        } else {
          value.forEach(function(item, i) {
            if (item !== null && typeof item === "object") {
              flatten(item, path + "." + i);
            } else {
              fields.push(path + "." + i);
            }
          });
        }
      } else if (typeof value === "object") {
        flatten(value, path);
      } else {
        fields.push(path);
      }
    }
  }

  flatten(product);

  // Write headers to row 1
  sheet.getRange(1, 1, 1, fields.length).setValues([fields]);
  sheet.getRange(1, 1, 1, fields.length).setFontWeight("bold");

  // Clear old data
  if (sheet.getLastRow() > 1) {
    sheet.getRange(2, 1, sheet.getLastRow() - 1, sheet.getLastColumn()).clearContent();
  }

  SpreadsheetApp.getUi().alert(`Done! ${fields.length} field headers written to row 1.\nIncludes all metafield definitions.`);
}
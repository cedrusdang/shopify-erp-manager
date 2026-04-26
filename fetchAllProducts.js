function fetchAllProducts(store, token) {
  let all = [];
  let nextUrl = `https://${store}/admin/api/2024-10/products.json?limit=250`;
  let page = 1;

  while (nextUrl) {
    SpreadsheetApp.getActive().toast(`Loading page ${page}... Loaded so far: ${all.length}`);

    const res = UrlFetchApp.fetch(nextUrl, {
      method: "get",
      headers: {
        "X-Shopify-Access-Token": token,
        "Content-Type": "application/json"
      }
    });

    const data = JSON.parse(res.getContentText());
    all = all.concat(data.products || []);

    const link = res.getHeaders()["Link"];
    if (link && link.includes('rel="next"')) {
      const match = link.match(/<([^>]+)>;\s*rel="next"/);
      nextUrl = match ? match[1] : null;
    } else {
      nextUrl = null;
    }

    page++;
  }

  return all;
}

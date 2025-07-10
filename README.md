# CenFin

This project manages personal finances with Django.

Exchange rate data can be loaded from [Frankfurter](https://www.frankfurter.app/), which updates daily around 16:00 CET and supports about 180 currencies.

The exchange-rate form now reuses the services layer on the server side as well,
so valid ISO currency codes from those APIs can be saved without hard-coded
choices.

When making `fetch()` requests to Django views that are protected by CSRF or
`login_required`, include credentials and the CSRF token:

```javascript
fetch(url, {
  method: 'GET',
  credentials: 'same-origin',
  headers: {
    'X-CSRFToken': getCookie('csrftoken'),
    'Accept': 'application/json'
  }
});
```

document.querySelectorAll('[data-variant-form]').forEach((form) => {
  const select = form.querySelector('[data-variant-select]'); const quantity = form.querySelector('[name="quantity"]');
  const sync = () => { const option = select.options[select.selectedIndex]; quantity.max = option.dataset.stock || 1; form.action = `/carrito/agregar/${option.value}/`; };
  select.addEventListener('change', sync); sync();
});
document.querySelectorAll('.checkout-form input, .checkout-form select, .checkout-form textarea, .auth-card input').forEach((field) => field.classList.add(field.tagName === 'SELECT' ? 'form-select' : 'form-control'));

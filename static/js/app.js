(function () {
  var themeStorageKey = 'nephewcrm-theme';

  function getTheme() {
    return localStorage.getItem(themeStorageKey) || 'light';
  }

  function applyTheme(theme) {
    document.documentElement.setAttribute('data-bs-theme', theme);
    localStorage.setItem(themeStorageKey, theme);

    document.querySelectorAll('[data-theme-toggle] i').forEach(function (icon) {
      icon.className = theme === 'dark' ? 'bi bi-sun-fill' : 'bi bi-moon-stars-fill';
    });
  }

  function toggleTheme() {
    applyTheme(getTheme() === 'dark' ? 'light' : 'dark');
  }

  function togglePassword(trigger) {
    var selector = trigger.getAttribute('data-password-toggle');
    if (!selector) {
      return;
    }

    var field = document.querySelector(selector);
    if (!field) {
      return;
    }

    var isPassword = field.getAttribute('type') === 'password';
    field.setAttribute('type', isPassword ? 'text' : 'password');

    var icon = trigger.querySelector('i');
    if (icon) {
      icon.className = isPassword ? 'bi bi-eye-slash' : 'bi bi-eye';
    }
  }

  function copyText(trigger) {
    var text = trigger.getAttribute('data-copy-text');
    if (!text || !navigator.clipboard) {
      return;
    }

    navigator.clipboard.writeText(text).then(function () {
      var original = trigger.innerHTML;
      trigger.innerHTML = '<i class="bi bi-check2"></i>';

      window.setTimeout(function () {
        trigger.innerHTML = original;
      }, 1600);
    });
  }

  function normalizeFilterText(value) {
    return String(value == null ? '' : value)
      .toLowerCase()
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .trim();
  }

  function initLoadingForms() {
    document.querySelectorAll('form[data-loading-form]').forEach(function (form) {
      if (form.hasAttribute('data-async-list-form')) {
        return;
      }

      form.addEventListener('submit', function () {
        var submitButton = form.querySelector('[type="submit"]');
        var loadingText = form.getAttribute('data-loading-text') || 'Carregando...';

        if (!submitButton || submitButton.disabled) {
          return;
        }

        submitButton.dataset.originalText = submitButton.innerHTML;
        submitButton.disabled = true;
        submitButton.innerHTML = '<span class="spinner-border spinner-border-sm" aria-hidden="true"></span><span>' + loadingText + '</span>';
        submitButton.classList.add('d-inline-flex', 'align-items-center', 'gap-2');
        form.setAttribute('aria-busy', 'true');
      });
    });
  }

  function initSelectAllCheckboxes() {
    document.querySelectorAll('[data-select-all]').forEach(function (toggle) {
      if (toggle.dataset.selectAllBound === 'true') {
        return;
      }

      toggle.dataset.selectAllBound = 'true';
      toggle.addEventListener('change', function () {
        var group = toggle.dataset.selectAll;
        document.querySelectorAll('[data-checkbox-group="' + group + '"]').forEach(function (checkbox) {
          checkbox.checked = toggle.checked;
        });
      });
    });
  }

  function initCheckboxSelectionButtons() {
    document.querySelectorAll('[data-checkbox-selection-action]').forEach(function (trigger) {
      if (trigger.dataset.checkboxSelectionBound === 'true') {
        return;
      }

      trigger.dataset.checkboxSelectionBound = 'true';
      trigger.addEventListener('click', function () {
        var action = trigger.getAttribute('data-checkbox-selection-action');
        var targetSelector = trigger.getAttribute('data-checkbox-selection-target');
        var inputName = trigger.getAttribute('data-checkbox-selection-name') || 'person_public_ids';
        var groupName = trigger.getAttribute('data-checkbox-selection-group') || '';
        var target = targetSelector ? document.querySelector(targetSelector) : null;
        var selectAllToggle = groupName ? document.querySelector('[data-select-all="' + groupName + '"]') : null;

        if (!target) {
          return;
        }

        if (action === 'clear') {
          target.querySelectorAll('input[name="' + inputName + '"]').forEach(function (checkbox) {
            checkbox.checked = false;
          });
          if (selectAllToggle) {
            selectAllToggle.checked = false;
          }
        }
      });
    });
  }

  function initAsyncListForms() {
    document.querySelectorAll('form[data-async-list-form]').forEach(function (form) {
      if (form.dataset.asyncListBound === 'true') {
        return;
      }

      form.dataset.asyncListBound = 'true';
      form.addEventListener('submit', function (event) {
        var submitButton = form.querySelector('[type="submit"]');
        var loadingText = form.getAttribute('data-loading-text') || 'Carregando...';
        var targetSelector = form.getAttribute('data-async-target');
        var requestUrl = form.getAttribute('action') || window.location.pathname;
        var formData = new FormData(form);
        var queryString = new URLSearchParams(formData).toString();
        var fetchUrl = queryString ? requestUrl + '?' + queryString : requestUrl;

        if (!targetSelector || !submitButton || submitButton.disabled) {
          return;
        }

        event.preventDefault();
        submitButton.disabled = true;
        submitButton.dataset.originalText = submitButton.innerHTML;
        submitButton.innerHTML = '<span class="spinner-border spinner-border-sm" aria-hidden="true"></span><span>' + loadingText + '</span>';
        submitButton.classList.add('d-inline-flex', 'align-items-center', 'gap-2');
        form.setAttribute('aria-busy', 'true');

        fetch(fetchUrl, {
          method: 'GET',
          credentials: 'same-origin',
          headers: {
            'X-Requested-With': 'XMLHttpRequest'
          }
        })
          .then(function (response) {
            return response.text().then(function (html) {
              return { ok: response.ok, html: html };
            });
          })
          .then(function (result) {
            if (!result.ok) {
              throw new Error('Nao foi possivel atualizar a listagem.');
            }

            var parser = new DOMParser();
            var nextDocument = parser.parseFromString(result.html, 'text/html');
            var currentTarget = document.querySelector(targetSelector);
            var nextTarget = nextDocument.querySelector(targetSelector);

            if (!currentTarget || !nextTarget) {
              throw new Error('Nao foi possivel localizar a area da listagem.');
            }

            currentTarget.outerHTML = nextTarget.outerHTML;
            initSelectAllCheckboxes();
            initListFilters();
            initLoadingForms();
            initAsyncListForms();
            initEnhancedMultiSelects();
            initRemoteSelects();
            initAutoOpenModals();
            initConfirmationSubmitButtons();
          })
          .catch(function () {
            if (crmErrorModal) {
              crmErrorModal.open({
                title: 'Falha ao atualizar a listagem',
                message: 'Nao foi possivel atualizar os dados desta tela agora.',
                details: 'Tente novamente em instantes.'
              });
            }
          })
          .finally(function () {
            if (submitButton.isConnected) {
              submitButton.disabled = false;
              if (submitButton.dataset.originalText) {
                submitButton.innerHTML = submitButton.dataset.originalText;
              }
            }
            form.removeAttribute('aria-busy');
          });
      });
    });
  }

  function initListFilters() {
    document.querySelectorAll('[data-filter-target]').forEach(function (input) {
      var targetSelector = input.getAttribute('data-filter-target');
      var itemSelector = input.getAttribute('data-filter-item') || '[data-filter-item]';

      function applyFilter() {
        var query = normalizeFilterText(input.value);
        var target = document.querySelector(targetSelector);
        if (!target) {
          return;
        }

        target.querySelectorAll(itemSelector).forEach(function (item) {
          var haystack = normalizeFilterText(item.getAttribute('data-filter-text') || item.textContent);
          item.classList.toggle('d-none', query && haystack.indexOf(query) === -1);
        });
      }

      input.addEventListener('input', applyFilter);
      applyFilter();
    });
  }

  function initEnhancedMultiSelects() {
    if (typeof TomSelect === 'undefined') {
      return;
    }

    document.querySelectorAll('select[data-enhanced-multiselect="true"]').forEach(function (select) {
      if (select.tomselect) {
        return;
      }

      new TomSelect(select, {
        plugins: {
          remove_button: {
            title: 'Remover item'
          }
        },
        create: false,
        hidePlaceholder: true,
        closeAfterSelect: false,
        maxOptions: null,
        placeholder: select.getAttribute('data-placeholder') || 'Pesquisar',
        render: {
          no_results: function (data, escape) {
            return '<div class="no-results">Nenhum resultado para "' + escape(data.input) + '".</div>';
          }
        }
      });
    });
  }

  function initRemoteSelects() {
    if (typeof TomSelect === 'undefined') {
      return;
    }

    document.querySelectorAll('select[data-remote-select="true"]').forEach(function (select) {
      if (select.tomselect) {
        return;
      }

      var remoteUrl = select.getAttribute('data-remote-url');
      var minChars = parseInt(select.getAttribute('data-remote-min-chars') || '1', 10);

      if (!remoteUrl) {
        return;
      }

      new TomSelect(select, {
        valueField: 'value',
        labelField: 'label',
        searchField: 'label',
        create: false,
        maxItems: 1,
        allowEmptyOption: true,
        preload: minChars === 0,
        placeholder: select.getAttribute('data-placeholder') || 'Pesquisar',
        load: function (query, callback) {
          if (query.length < minChars && !(minChars === 0 && query.length === 0)) {
            callback();
            return;
          }

          fetch(remoteUrl + '?q=' + encodeURIComponent(query), {
            method: 'GET',
            credentials: 'same-origin',
            headers: {
              'X-Requested-With': 'XMLHttpRequest'
            }
          })
            .then(function (response) {
              if (!response.ok) {
                throw new Error('Falha ao carregar opcoes.');
              }
              return response.json();
            })
            .then(function (payload) {
              callback(payload.results || []);
            })
            .catch(function () {
              callback();
            });
        },
        render: {
          no_results: function (data, escape) {
            return '<div class="no-results">Nenhum resultado para "' + escape(data.input) + '".</div>';
          }
        }
      });
    });
  }

  function initAutoOpenModals() {
    if (typeof bootstrap === 'undefined') {
      return;
    }

    document.querySelectorAll('[data-auto-open-modal]').forEach(function (trigger) {
      var modalId = trigger.getAttribute('data-auto-open-modal');
      var shouldOpenOnce = trigger.getAttribute('data-auto-open-modal-once') === 'true';
      var modalElement = modalId ? document.getElementById(modalId) : null;
      var existingBodyModal = modalId ? document.body.querySelector('[id="' + modalId + '"]') : null;

      if (!modalElement) {
        return;
      }

      if (shouldOpenOnce && trigger.dataset.autoOpenHandled === 'true') {
        return;
      }

      if (existingBodyModal && existingBodyModal !== modalElement) {
        existingBodyModal.remove();
      }

      if (modalElement.parentElement !== document.body) {
        document.body.appendChild(modalElement);
      }

      trigger.dataset.autoOpenHandled = 'true';
      window.setTimeout(function () {
        bootstrap.Modal.getOrCreateInstance(modalElement).show();
      }, 150);
    });
  }

  function initConfirmationSubmitButtons() {
    document.querySelectorAll('[data-confirm-submit-target]').forEach(function (button) {
      if (button.dataset.confirmSubmitBound === 'true') {
        return;
      }

      button.dataset.confirmSubmitBound = 'true';
      button.addEventListener('click', function () {
        var formSelector = button.getAttribute('data-confirm-submit-target');
        var fieldSelector = button.getAttribute('data-confirm-set-field');
        var fieldValue = button.getAttribute('data-confirm-set-value') || '1';
        var form = formSelector ? document.querySelector(formSelector) : null;
        var field = fieldSelector && form ? form.querySelector(fieldSelector) : null;

        if (!form) {
          return;
        }

        if (field) {
          field.value = fieldValue;
        }

        window.setTimeout(function () {
          form.requestSubmit();
        }, 120);
      });
    });
  }

  function escapeHtml(value) {
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function initCrmErrorModal() {
    var modalElement = document.getElementById('crmErrorModal');

    if (!modalElement || typeof bootstrap === 'undefined') {
      return null;
    }

    var modal = bootstrap.Modal.getOrCreateInstance(modalElement);
    var titleElement = document.getElementById('crmErrorModalLabel');
    var messageElement = document.getElementById('crmErrorModalMessage');
    var detailsElement = document.getElementById('crmErrorModalDetails');

    return {
      open: function (options) {
        var title = options && options.title ? options.title : 'Nao foi possivel concluir a operacao';
        var message = options && options.message ? options.message : 'Ocorreu um erro inesperado.';
        var details = options && options.details ? options.details : '';

        if (titleElement) {
          titleElement.textContent = title;
        }
        if (messageElement) {
          messageElement.textContent = message;
        }
        if (detailsElement) {
          detailsElement.textContent = details;
          detailsElement.classList.toggle('d-none', !details);
        }

        modal.show();
      }
    };
  }

  function initApiKeyRevealFlow() {
    var modalElement = document.getElementById('apiKeyRevealModal');
    var form = document.getElementById('apiKeyRevealForm');

    if (!modalElement || !form || typeof bootstrap === 'undefined') {
      return null;
    }

    var modal = bootstrap.Modal.getOrCreateInstance(modalElement);
    var subtitle = document.getElementById('apiKeyRevealModalSubtitle');
    var errorBox = document.getElementById('apiKeyRevealError');
    var resultBox = document.getElementById('apiKeyRevealResult');
    var valueBox = document.getElementById('apiKeyRevealValue');
    var maskedValueBox = document.getElementById('apiKeyRevealMaskedValue');
    var copyButton = document.getElementById('apiKeyRevealCopyButton');
    var submitButton = form.querySelector('button[type="submit"]');
    var confirmationField = form.querySelector('input[name="confirmation_word"]');
    var csrfField = form.querySelector('input[name="csrfmiddlewaretoken"]');
    var state = {
      maskedValue: '',
      appName: '',
      revealUrl: ''
    };

    function resetRevealModal() {
      form.reset();
      if (subtitle) {
        subtitle.textContent = 'Digite a palavra de confirmacao para continuar.';
      }
      if (errorBox) {
        errorBox.classList.add('d-none');
        errorBox.textContent = '';
      }
      if (resultBox) {
        resultBox.classList.add('d-none');
      }
      if (valueBox) {
        valueBox.textContent = '';
      }
      if (maskedValueBox) {
        maskedValueBox.textContent = '';
      }
      if (copyButton) {
        copyButton.removeAttribute('data-copy-text');
        copyButton.setAttribute('disabled', 'disabled');
      }
      if (submitButton) {
        submitButton.disabled = false;
      }
    }

    function openRevealModal(trigger) {
      state.revealUrl = trigger.getAttribute('data-reveal-url') || '';
      state.appName = trigger.getAttribute('data-app-name') || 'este aplicativo';
      state.maskedValue = trigger.getAttribute('data-masked-value') || '';

      resetRevealModal();

      if (subtitle) {
        subtitle.textContent = 'Digite "mostrar" para solicitar a chave descriptografada de ' + state.appName + '.';
      }

      modal.show();
      if (confirmationField) {
        window.setTimeout(function () {
          confirmationField.focus();
        }, 150);
      }
    }

    function renderError(message) {
      if (!errorBox) {
        return;
      }

      errorBox.textContent = message;
      errorBox.classList.remove('d-none');
    }

    function renderResult(payload) {
      if (!resultBox || !valueBox || !maskedValueBox) {
        return;
      }

      valueBox.textContent = payload.api_key;
      maskedValueBox.textContent = payload.masked_value || state.maskedValue;
      resultBox.classList.remove('d-none');

      if (copyButton) {
        copyButton.setAttribute('data-copy-text', payload.api_key);
        copyButton.removeAttribute('disabled');
      }
    }

    modalElement.addEventListener('hidden.bs.modal', resetRevealModal);

    form.addEventListener('submit', function (event) {
      var formData;
      var csrfToken;

      event.preventDefault();

      if (!state.revealUrl) {
        renderError('Nao foi possivel preparar a solicitacao segura de exibicao.');
        return;
      }

      if (submitButton) {
        submitButton.disabled = true;
      }

      if (errorBox) {
        errorBox.classList.add('d-none');
        errorBox.textContent = '';
      }
      if (resultBox) {
        resultBox.classList.add('d-none');
      }

      formData = new FormData(form);
      csrfToken = csrfField ? csrfField.value : '';

      fetch(state.revealUrl, {
        method: 'POST',
        credentials: 'same-origin',
        cache: 'no-store',
        headers: {
          'X-CSRFToken': csrfToken,
          'X-Requested-With': 'XMLHttpRequest'
        },
        body: new URLSearchParams(formData)
      })
        .then(function (response) {
          return response.json().then(function (payload) {
            return {
              ok: response.ok,
              payload: payload,
              status: response.status
            };
          });
        })
        .then(function (result) {
          if (!result.ok) {
            renderError(result.payload.detail || 'Nao foi possivel exibir a chave de API.');
            return;
          }

          renderResult(result.payload);
        })
        .catch(function () {
          renderError('Nao foi possivel exibir a chave de API agora. Tente novamente.');
        })
        .finally(function () {
          if (submitButton) {
            submitButton.disabled = false;
          }
        });
    });

    return {
      openRevealModal: openRevealModal
    };
  }

  function initBotConversaDispatchPoller() {
    var pollerForm = document.getElementById('botConversaDispatchPoller');

    if (!pollerForm) {
      return null;
    }

    var csrfField = pollerForm.querySelector('input[name="csrfmiddlewaretoken"]');
    var pollUrlField = pollerForm.querySelector('input[name="poll_url"]');
    var isFinishedField = pollerForm.querySelector('input[name="is_finished"]');
    var progressBar = document.getElementById('dispatchProgressBar');
    var progressValue = document.getElementById('dispatchProgressValue');
    var processedCount = document.getElementById('dispatchProcessedCount');
    var totalCount = document.getElementById('dispatchTotalCount');
    var successCount = document.getElementById('dispatchSuccessCount');
    var failedCount = document.getElementById('dispatchFailedCount');
    var statusLabel = document.getElementById('dispatchStatusLabel');
    var statusBadge = document.getElementById('dispatchStatusBadge');
    var itemsTableBody = document.getElementById('dispatchItemsTableBody');
    var nextPollDelayField = pollerForm.querySelector('input[name="next_poll_delay_ms"]');
    var timerId = null;
    var isPolling = false;

    function humanizeStatus(status) {
      var statusMap = {
        pending: 'Pendente',
        running: 'Em andamento',
        completed: 'Concluido',
        completed_with_errors: 'Concluido com erros',
        failed: 'Falhou',
        success: 'Sucesso',
        skipped: 'Ignorado',
        active: 'Ativo',
        inactive: 'Inativo',
        revoked: 'Revogado',
        synced: 'Sincronizado',
        stale: 'Desatualizado',
        error: 'Erro',
        archived: 'Arquivado',
        available: 'Disponivel',
        used: 'Usado',
        expired: 'Expirado'
      };

      return statusMap[String(status || '').toLowerCase()] || String(status || '')
        .replace(/_/g, ' ')
        .replace(/\b\w/g, function (character) {
          return character.toUpperCase();
        });
    }

    function renderItems(items) {
      if (!itemsTableBody) {
        return;
      }

      itemsTableBody.innerHTML = items.map(function (item) {
        var errorMessage = escapeHtml(item.error_message || '-');

        return (
          '<tr>' +
            '<td>' + escapeHtml(item.target_name) + '</td>' +
            '<td>' + escapeHtml(item.target_phone) + '</td>' +
            '<td><span class="status-badge status-used">' + escapeHtml(humanizeStatus(item.status)) + '</span></td>' +
            '<td class="small text-body-secondary">' + errorMessage + '</td>' +
          '</tr>'
        );
      }).join('');
    }

    function renderPayload(payload) {
      if (progressBar) {
        progressBar.style.width = payload.progress_percent + '%';
      }
      if (progressValue) {
        progressValue.textContent = payload.progress_percent + '%';
      }
      if (processedCount) {
        processedCount.textContent = payload.processed_items;
      }
      if (totalCount) {
        totalCount.textContent = payload.total_items;
      }
      if (successCount) {
        successCount.textContent = payload.success_items;
      }
      if (failedCount) {
        failedCount.textContent = payload.failed_items;
      }
      if (statusLabel) {
        statusLabel.textContent = humanizeStatus(payload.status);
      }
      if (statusBadge) {
        statusBadge.textContent = humanizeStatus(payload.status);
      }
      if (Array.isArray(payload.items)) {
        renderItems(payload.items);
      }
      if (nextPollDelayField && payload.next_poll_delay_ms != null) {
        nextPollDelayField.value = String(payload.next_poll_delay_ms);
      }

      if (payload.is_finished && isFinishedField) {
        isFinishedField.value = 'true';
      }
    }

    function scheduleNextPoll() {
      if (!isFinishedField || isFinishedField.value === 'true') {
        return;
      }

      timerId = window.setTimeout(runPoll, Number(nextPollDelayField && nextPollDelayField.value ? nextPollDelayField.value : 1600));
    }

    function runPoll() {
      var csrfToken;
      var pollUrl;

      if (isPolling || !pollUrlField || !csrfField || !isFinishedField || isFinishedField.value === 'true') {
        return;
      }

      pollUrl = pollUrlField.value;
      csrfToken = csrfField.value;
      isPolling = true;

      fetch(pollUrl, {
        method: 'POST',
        credentials: 'same-origin',
        cache: 'no-store',
        headers: {
          'X-CSRFToken': csrfToken,
          'X-Requested-With': 'XMLHttpRequest'
        }
      })
        .then(function (response) {
          return response.json().then(function (payload) {
            return {
              ok: response.ok,
              payload: payload
            };
          });
        })
        .then(function (result) {
          if (!result.ok) {
            if (crmErrorModal) {
              crmErrorModal.open({
                title: 'Erro no processamento do disparo',
                message: 'O dispatch nao pode continuar neste momento.',
                details: result.payload && result.payload.detail ? result.payload.detail : 'Verifique a configuracao e tente novamente.'
              });
            }
            if (isFinishedField) {
              isFinishedField.value = 'true';
            }
            return;
          }

          renderPayload(result.payload);
        })
        .catch(function () {
          if (crmErrorModal) {
            crmErrorModal.open({
              title: 'Erro de comunicacao com o dispatch',
              message: 'Nao foi possivel atualizar o status do disparo.',
              details: 'A conexao com o backend falhou durante o polling.'
            });
          }
          if (isFinishedField) {
            isFinishedField.value = 'true';
          }
        })
        .finally(function () {
          isPolling = false;
          scheduleNextPoll();
        });
    }

    if (isFinishedField.value !== 'true') {
      scheduleNextPoll();
    }

    return {
      stop: function () {
        if (timerId) {
          window.clearTimeout(timerId);
        }
      }
    };
  }

  function initGmailDispatchPoller() {
    var pollerForm = document.getElementById('gmailDispatchPoller');

    if (!pollerForm) {
      return null;
    }

    var csrfField = pollerForm.querySelector('input[name="csrfmiddlewaretoken"]');
    var pollUrlField = pollerForm.querySelector('input[name="poll_url"]');
    var isFinishedField = pollerForm.querySelector('input[name="is_finished"]');
    var nextPollDelayField = pollerForm.querySelector('input[name="next_poll_delay_ms"]');
    var processedCount = document.getElementById('gmailDispatchProcessedCount');
    var totalCount = document.getElementById('gmailDispatchTotalCount');
    var successCount = document.getElementById('gmailDispatchSuccessCount');
    var failedCount = document.getElementById('gmailDispatchFailedCount');
    var statusLabel = document.getElementById('gmailDispatchStatusLabel');
    var statusBadge = document.getElementById('gmailDispatchStatusBadge');
    var recipientsTableBody = document.getElementById('gmailDispatchRecipientsTableBody');
    var timerId = null;
    var isPolling = false;

    function humanizeStatus(status) {
      var statusMap = {
        pending: 'Pendente',
        running: 'Em andamento',
        completed: 'Concluido',
        completed_with_errors: 'Concluido com erros',
        failed: 'Falhou',
        sent: 'Enviado'
      };

      return statusMap[String(status || '').toLowerCase()] || String(status || '')
        .replace(/_/g, ' ')
        .replace(/\b\w/g, function (character) {
          return character.toUpperCase();
        });
    }

    function renderRecipients(recipients) {
      if (!recipientsTableBody) {
        return;
      }

      recipientsTableBody.innerHTML = recipients.map(function (recipient) {
        var errorBlock = recipient.error_message
          ? '<div class="text-danger small">' + escapeHtml(recipient.error_message) + '</div>'
          : '';

        return (
          '<tr>' +
            '<td>' + escapeHtml(recipient.person_name) + '</td>' +
            '<td>' + escapeHtml(recipient.email_snapshot) + '</td>' +
            '<td>' + escapeHtml(humanizeStatus(recipient.status)) + errorBlock + '</td>' +
            '<td class="small">' + escapeHtml(recipient.gmail_message_id || '-') + '</td>' +
            '<td class="small">' + escapeHtml(recipient.gmail_thread_id || '-') + '</td>' +
          '</tr>'
        );
      }).join('');
    }

    function renderPayload(payload) {
      if (processedCount) {
        processedCount.textContent = payload.processed_recipients;
      }
      if (totalCount) {
        totalCount.textContent = payload.total_recipients;
      }
      if (successCount) {
        successCount.textContent = payload.success_recipients;
      }
      if (failedCount) {
        failedCount.textContent = payload.failed_recipients;
      }
      if (statusLabel) {
        statusLabel.textContent = humanizeStatus(payload.status);
      }
      if (statusBadge) {
        statusBadge.textContent = humanizeStatus(payload.status);
      }
      if (nextPollDelayField && payload.next_poll_delay_ms != null) {
        nextPollDelayField.value = String(payload.next_poll_delay_ms);
      }
      if (Array.isArray(payload.recipients)) {
        renderRecipients(payload.recipients);
      }
      if (payload.is_finished && isFinishedField) {
        isFinishedField.value = 'true';
      }
    }

    function scheduleNextPoll() {
      if (!isFinishedField || isFinishedField.value === 'true') {
        return;
      }

      timerId = window.setTimeout(runPoll, Number(nextPollDelayField && nextPollDelayField.value ? nextPollDelayField.value : 1200));
    }

    function runPoll() {
      var csrfToken;
      var pollUrl;

      if (isPolling || !pollUrlField || !csrfField || !isFinishedField || isFinishedField.value === 'true') {
        return;
      }

      pollUrl = pollUrlField.value;
      csrfToken = csrfField.value;
      isPolling = true;

      fetch(pollUrl, {
        method: 'POST',
        credentials: 'same-origin',
        cache: 'no-store',
        headers: {
          'X-CSRFToken': csrfToken,
          'X-Requested-With': 'XMLHttpRequest'
        }
      })
        .then(function (response) {
          return response.json().then(function (payload) {
            return {
              ok: response.ok,
              payload: payload
            };
          });
        })
        .then(function (result) {
          if (!result.ok) {
            if (crmErrorModal) {
              crmErrorModal.open({
                title: 'Erro no processamento do disparo',
                message: 'O dispatch de Gmail nao pode continuar neste momento.',
                details: result.payload && result.payload.detail ? result.payload.detail : 'Verifique a configuracao e tente novamente.'
              });
            }
            if (isFinishedField) {
              isFinishedField.value = 'true';
            }
            return;
          }

          renderPayload(result.payload);
        })
        .catch(function () {
          if (crmErrorModal) {
            crmErrorModal.open({
              title: 'Erro de comunicacao com o dispatch',
              message: 'Nao foi possivel atualizar o status do disparo de Gmail.',
              details: 'A conexao com o backend falhou durante o polling.'
            });
          }
          if (isFinishedField) {
            isFinishedField.value = 'true';
          }
        })
        .finally(function () {
          isPolling = false;
          scheduleNextPoll();
        });
    }

    if (isFinishedField.value !== 'true') {
      scheduleNextPoll();
    }

    return {
      stop: function () {
        if (timerId) {
          window.clearTimeout(timerId);
        }
      }
    };
  }

  function initDispatchAudienceFilters() {
    document.querySelectorAll('[data-audience-url]').forEach(function (trigger) {
      if (trigger.dataset.audienceBound === 'true') {
        return;
      }

      trigger.dataset.audienceBound = 'true';
        trigger.addEventListener('click', function () {
          var audienceUrl = trigger.getAttribute('data-audience-url');
          var targetSelector = trigger.getAttribute('data-audience-target');
          var emptySelector = trigger.getAttribute('data-empty-target');
          var countSelector = trigger.getAttribute('data-count-target');
          var tagFieldSelector = trigger.getAttribute('data-tag-field');
          var channelLabel = trigger.getAttribute('data-channel-label') || 'canal';
          var onlyUnsent = trigger.getAttribute('data-only-unsent') === 'true' ? '0' : '1';
          var target = targetSelector ? document.querySelector(targetSelector) : null;
          var emptyState = emptySelector ? document.querySelector(emptySelector) : null;
          var emptyMessage = emptyState ? emptyState.querySelector('p') : null;
          var countTarget = countSelector ? document.querySelector(countSelector) : null;
          var tagField = tagFieldSelector ? document.querySelector(tagFieldSelector) : null;
          var checkboxGroup = target.getAttribute('data-checkbox-group') || '';
          var selectedValues = [];
          var originalText = trigger.textContent;
          var query = new URLSearchParams();

          if (!audienceUrl || !target || trigger.disabled) {
            return;
          }

        target.querySelectorAll('input[name="person_public_ids"]:checked').forEach(function (input) {
          selectedValues.push(input.value);
        });

          trigger.disabled = true;
          trigger.textContent = 'Atualizando...';

          query.set('only_unsent', onlyUnsent);
          if (tagField) {
            tagField.querySelectorAll('input[name="tag_public_ids"]:checked').forEach(function (input) {
              query.append('tag_public_ids', input.value);
            });
          }

          fetch(audienceUrl + '?' + query.toString(), {
            method: 'GET',
            credentials: 'same-origin',
            cache: 'no-store',
            headers: {
            'X-Requested-With': 'XMLHttpRequest'
          }
        })
          .then(function (response) {
            return response.json().then(function (payload) {
              return {
                ok: response.ok,
                payload: payload
              };
            });
          })
          .then(function (result) {
            var payload = result.payload || {};

            if (!result.ok) {
              throw new Error(payload.detail || 'Nao foi possivel atualizar a audiencia.');
            }

            target.innerHTML = (payload.items || []).map(function (item) {
              var isChecked = selectedValues.indexOf(item.value) >= 0;
              var checkboxGroupAttr = checkboxGroup ? ' data-checkbox-group="' + escapeHtml(checkboxGroup) + '"' : '';

              return (
                '<label class="bot-selection-card" data-filter-item data-filter-text="' + escapeHtml(item.label) + '">' +
                  '<input class="bot-selection-checkbox" type="checkbox" name="person_public_ids" value="' + escapeHtml(item.value) + '"' + checkboxGroupAttr + (isChecked ? ' checked' : '') + '>' +
                  '<span class="bot-selection-text">' + escapeHtml(item.label) + '</span>' +
                '</label>'
              );
            }).join('');

            target.classList.toggle('d-none', (payload.items || []).length === 0);

            if (emptyState) {
              emptyState.classList.toggle('d-none', (payload.items || []).length > 0);
            }
            if (emptyMessage) {
              emptyMessage.textContent = payload.empty_message || '';
            }
            if (countTarget) {
              countTarget.textContent = String(payload.count || 0) + ' disponiveis';
            }

            trigger.setAttribute('data-only-unsent', payload.only_unsent ? 'true' : 'false');
            trigger.textContent = payload.only_unsent ? 'Mostrar todos' : 'Mostrar apenas nao enviados';
            initListFilters();
          })
          .catch(function (error) {
            trigger.textContent = originalText;
            if (crmErrorModal) {
              crmErrorModal.open({
                title: 'Falha ao atualizar a audiencia',
                message: 'Nao foi possivel carregar as pessoas elegiveis para ' + channelLabel + '.',
                details: error && error.message ? error.message : 'Tente novamente em instantes.'
              });
            }
          })
          .finally(function () {
            trigger.disabled = false;
            if (trigger.textContent === 'Atualizando...') {
              trigger.textContent = originalText;
            }
          });
      });
    });
  }

  var apiKeyRevealFlow = null;
  var botConversaDispatchPoller = null;
  var gmailDispatchPoller = null;
  var crmErrorModal = null;

  document.addEventListener('click', function (event) {
    var themeTrigger = event.target.closest('[data-theme-toggle]');
    if (themeTrigger) {
      toggleTheme();
      return;
    }

    var passwordTrigger = event.target.closest('[data-password-toggle]');
    if (passwordTrigger) {
      togglePassword(passwordTrigger);
      return;
    }

    var revealTrigger = event.target.closest('[data-reveal-trigger]');
    if (revealTrigger) {
      if (apiKeyRevealFlow) {
        apiKeyRevealFlow.openRevealModal(revealTrigger);
      }
      return;
    }

    var copyTrigger = event.target.closest('[data-copy-text]');
    if (copyTrigger) {
      copyText(copyTrigger);
    }
  });

  crmErrorModal = initCrmErrorModal();
  apiKeyRevealFlow = initApiKeyRevealFlow();
  botConversaDispatchPoller = initBotConversaDispatchPoller();
  gmailDispatchPoller = initGmailDispatchPoller();
  initSelectAllCheckboxes();
  initCheckboxSelectionButtons();
  initLoadingForms();
  initListFilters();
  initAsyncListForms();
  initDispatchAudienceFilters();
  initEnhancedMultiSelects();
  initRemoteSelects();
  initAutoOpenModals();
  initConfirmationSubmitButtons();
  applyTheme(getTheme());
}());

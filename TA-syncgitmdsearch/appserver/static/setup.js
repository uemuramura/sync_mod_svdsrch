require([
  "jquery",
  "splunkjs/mvc",
  "splunkjs/mvc/simplexml/ready!"
], function ($, mvc) {
  var service = mvc.createService({ owner: "nobody" });
  var $status = $("#sgms-status");
  var $save = $("#sgms-save");
  var endpoint = "syncgitmdsearch_settings/git";

  function setStatus(kind, text) {
    $status.removeClass("is-ok is-error");
    if (kind) {
      $status.addClass("is-" + kind);
    }
    $status.text(text || "");
  }

  function boolFromConf(value) {
    return value === true || value === "true" || value === "1";
  }

  function toggleAuthFields() {
    var basic = $("#sgms-auth-type").val() === "https_basic";
    $("#sgms-username, #sgms-username-label").toggle(basic);
  }

  function applyContent(content) {
    $("#sgms-repo-url").val(content.repo_url || "");
    $("#sgms-provider").val(content.provider || "auto");
    $("#sgms-api-base").val(content.api_base_url || "");
    $("#sgms-branch").val(content.branch || "main");
    $("#sgms-md-glob").val(content.md_glob || "**/*.md");
    $("#sgms-auth-type").val(content.auth_type === "https_basic" ? "https_basic" : "https_token");
    $("#sgms-username").val(content.username || "");
    $("#sgms-target-app").val(content.target_app || "TA-syncgitmdsearch");
    $("#sgms-target-owner").val(content.target_owner || "nobody");
    $("#sgms-overwrite").prop("checked", boolFromConf(content.overwrite));
    $("#sgms-password").val("");
    $("#sgms-password-hint").text(
      content.password_set === "1" ? "保存済みのシークレットがあります。変更する場合のみ入力してください。" : "公開リポジトリなら空でも構いません。"
    );
    toggleAuthFields();
  }

  function loadSettings(okMessage) {
    setStatus("", "設定を読み込み中...");
    service.get(endpoint, { output_mode: "json" }, function (err, response) {
      if (err) {
        setStatus("error", "設定の読み込みに失敗しました。管理者権限で開いてください。");
        return;
      }
      var entry = (((response || {}).data || {}).entry || [])[0] || {};
      applyContent(entry.content || {});
      setStatus("ok", okMessage || "現在の設定を表示しています。");
    });
  }

  $("#sgms-auth-type").on("change", toggleAuthFields);

  $save.on("click", function (event) {
    event.preventDefault();
    var payload = {
      repo_url: $("#sgms-repo-url").val().trim(),
      provider: $("#sgms-provider").val(),
      api_base_url: $("#sgms-api-base").val().trim(),
      branch: $("#sgms-branch").val().trim(),
      md_glob: $("#sgms-md-glob").val().trim(),
      auth_type: $("#sgms-auth-type").val(),
      username: $("#sgms-username").val().trim(),
      target_app: $("#sgms-target-app").val().trim(),
      target_owner: $("#sgms-target-owner").val().trim(),
      overwrite: $("#sgms-overwrite").is(":checked") ? "1" : "0"
    };
    var password = $("#sgms-password").val();
    if (password) {
      payload.password = password;
    }
    $save.prop("disabled", true);
    setStatus("", "保存しています...");
    service.post(endpoint, payload, function (err) {
      $save.prop("disabled", false);
      $("#sgms-password").val("");
      if (err) {
        var detail = (err.data && err.data.messages && err.data.messages[0] && err.data.messages[0].text) || err.error || "保存に失敗しました。";
        setStatus("error", String(detail));
        return;
      }
      setStatus("ok", "設定を保存しました。セットアップを完了しています...");
      window.location.href = _syncViewUrl();
    });
  });

  function _syncViewUrl() {
    var parts = window.location.pathname.split("/");
    if (parts.length >= 2) {
      parts[parts.length - 1] = "sync";
      return parts.join("/") + window.location.search;
    }
    return "sync";
  }

  loadSettings();
});

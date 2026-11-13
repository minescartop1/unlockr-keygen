/*
 * Захват Play Integrity токена из запущенного Unlock-r.
 *
 * Токен запрашивается в Lfg/c;->b(...) и кладётся в запрос как query-параметр
 * "integrityToken" через хелпер Lwc/a;->B(request, name, value).
 * Хукаем именно хелпер — он вызывается со всеми параметрами запроса,
 * так что нужное значение отлавливается без привязки к внутренностям SDK.
 *
 *   frida -U -f me.tito.unlocker -l capture_token.js --no-pause
 *   или: frida -U -n Unlock-r -l capture_token.js
 *
 * Токен прилетит в stdout как строка "INTEGRITY_TOKEN=<...>".
 * Его надо положить в integrity_token.txt рядом с keygen.py.
 */

'use strict';

Java.perform(function () {
    var A = Java.use('wc.a');
    var patched = false;

    A.B.implementation = function (request, name, value) {
        try {
            var key = name === null || name === undefined ? '' : name.toString();
            if (key === 'integrityToken' && value !== null && value !== undefined) {
                var token = value.toString();
                if (token.length > 20) {
                    console.log('INTEGRITY_TOKEN=' + token);
                }
            }
        } catch (e) {
            /* не мешаем приложению работать */
        }
        patched = true;
        return this.B(request, name, value);
    };

    console.log('[capture] hook wc.a.B установлен: ' + patched);

    /* подстраховка: если в новой версии поменяли хелпер — ловим сам SDK */
    try {
        var C = Java.use('fg.c');
        var orig = C.b.overload('java.lang.String', 'android.content.Context',
            'kotlin.coroutines.Continuation');
        orig.implementation = function (uid, ctx, cont) {
            var res = orig.call(this, uid, ctx, cont);
            if (res !== null && res !== undefined) {
                try {
                    var s = res.toString();
                    if (s.length > 20 && s.indexOf('.') > 0) {
                        console.log('INTEGRITY_TOKEN=' + s);
                    }
                } catch (e) {}
            }
            return res;
        };
        console.log('[capture] hook fg.c.b установлен');
    } catch (e) {
        console.log('[capture] fg.c.b недоступен: ' + e);
    }
});

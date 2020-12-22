// Reference: https://cdn.bootcdn.net/ajax/libs/Base64/1.1.0/base64.js
// This is a modified version for taking Uint8Array as input
function b64encode(input) {
    var chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=';
    for (var block, byteCode, idx = 0, map = chars, output = '';
        input.length > (idx | 0) || (map = '=', idx % 1);
        output += map.charAt(63 & block >> 8 - idx % 1 * 8))
        block = block << 8 | input[parseInt(idx += 3 / 4)];
    return output;
}

$(function() {

    var canvas = document.getElementById('canvas');
    var ctx = canvas.getContext('2d');

    ctx.fillRect(0, 0, canvas.width, canvas.height);

    $('#btn-open').click(function (e) {
        var ws = new WebSocket('ws://142857.red:3389/wsock');

        $('#btn-close').click(function (e) {
            ws.send('close');
            ws.close();
        });

        var lastx = 0, lasty = 0;

        function mouse(e, type, key) {
            e.preventDefault();
            var rect = $('#canvas').get()[0].getBoundingClientRect();
            var mx = e.clientX != undefined ? (e.clientX - rect.left) / (rect.right - rect.left) : lastx;
            var my = e.clientX != undefined ? 1 - (e.clientY - rect.top) / (rect.bottom - rect.top) : lasty;
            if (key == undefined) {
                key = ['MOVE', 'LMB', 'MMB', 'RMB'][e.which];
            }
            if (0 <= mx && mx <= 1 && 0 <= my && my <= 1) {
                ws.send(`key:${type}:${key}:${mx}:${my}:0:0`);
                lastx = mx;
                lasty = my;
            }
        }

        function keyevent(e, type) {
            console.log('key', e.keyCode);
            var k = String.fromCharCode(e.keyCode);
            mouse(e, type, k);
        }

        $(document).contextmenu(function (e) {
            e.preventDefault();
            return false;
        }).mousedown(function (e) {
            mouse(e, 'PRESS');
            return false;
        }).mouseup(function (e) {
            mouse(e, 'RELEASE');
            return false;
        }).mousemove(function (e) {
            mouse(e, 'MOTION', 'MOVE');
            return false;
        }).keydown(function (e) {
            keyevent(e, 'PRESS');
            return false;
        }).keyup(function (e) {
            keyevent(e, 'RELEASE');
            return false;
        });

        ws.onopen = function (e) {
            console.log('ws opened!');
        };

        ws.onclose = function (e) {
            console.log('ws closed!');
        };

        var lastTime = Date.now();
        function update(data, w, h) {
            var img = new Image(w, h);
            img.onload = function () {
                canvas.width = w;
                canvas.height = h;
                ctx.drawImage(img, 0, 0, w, h);

                var t = Date.now();
                $('#info-res').html(w + 'x' + h);
                $('#info-fps').html(Math.round(1000 / (t - lastTime)));
                $('#info-kib').html(data.length >> 10);
                lastTime = t;
            };
            img.src = 'data:image/jpeg;base64,' + data;
        }

        ws.onmessage = function (e) {
            // console.log('ws received:', e.data);

            if (e.data.stream != undefined) {
                e.data.stream().getReader().read().then(function (res) {
                    var data = res.value;
                    // the first two int32 is for width and height in little-endian:
                    var w = data[0] | data[1] << 8 | data[2] << 16 | data[3] << 24;
                    var h = data[4] | data[5] << 8 | data[6] << 16 | data[7] << 24;
                    // afterwards the real jpeg data starts:
                    data = data.subarray(8, data.length - 8);
                    data = b64encode(data);
                    update(data, w, h);
                });
                return;
            }

            var w = e.data.slice(0, 4) | 0;
            var h = e.data.slice(4, 8) | 0;
            var data = e.data.slice(8);
            update(data, w, h);
        };

        ws.onerror = function (e) {
            console.log('ws got error:', e);
        };
    });
});

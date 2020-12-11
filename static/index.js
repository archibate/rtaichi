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

    var ws = new WebSocket('ws://localhost:8123/wsock');

    $('#close').click(function (e) {
        console.log('close clicked:', e);
        ws.send('close');
        ws.close();
    });

    ws.onopen = function (e) {
        console.log('ws opened!');
    };

    ws.onclose = function (e) {
        console.log('ws closed!');
    };

    var lastTime = Date.now();
    ws.onmessage = function (e) {
        // console.log('ws received:', e.data);

        e.data.stream().getReader().read().then(function (res) {
            var data = res.value;
            // the first two int32 is for width and height in little-endian:
            var w = data[0] | data[1] << 8 | data[2] << 16 | data[3] << 24;
            var h = data[4] | data[5] << 8 | data[6] << 16 | data[7] << 24;
            // afterwards the real jpeg data starts:
            data = data.subarray(8, data.length - 8);
            // console.log(data.length >> 10, 'KiB');
            var b64_data = b64encode(data);

            var img = new Image(w, h);
            img.onload = function () {
                canvas.width = w;
                canvas.height = h;
                ctx.drawImage(img, 0, 0, w, h);

                var t = Date.now();
                // console.log(Math.round(1000 / (t - lastTime)), 'FPS');
                lastTime = t;
            };
            img.src = 'data:image/jpeg;base64,' + b64_data;
        });
    };

    ws.onerror = function (e) {
        console.log('ws got error:', e.data);
    };

});

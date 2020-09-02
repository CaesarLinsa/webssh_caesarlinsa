//获取主机 端口
webhost=location.hostname;
webport=location.port;

var socket;
var term = new Terminal({
    "cursorBlink":true,
    "rows":200,
    "cols":140,
});


function ws_connect(e){
    $.get(url = "/login",
        data = {
            "id": e.getAttribute('id')
        },
        function (msg) {
            console.log(msg);
        });
}

function success_execute(msg){
        if(msg.id){
            container = document.getElementById('term');
            url = 'ws://'+ webhost +':'+ webport +'/ws?id=' + msg.id;
            socket = new WebSocket(url);
            $('#term').html("");
            term.onData(function(data) {
            //控制台输入字符
            console.log(data);
            socket.send(JSON.stringify({'data':data}));
            });

            socket.onopen = function(){
                $('.panel').show();
                $('#term').show();
                term.open(container, true);
                console.log(term);
            };

            socket.onmessage = function (event) {
                decoder = new window.TextDecoder('utf-8');
                var reader = new FileReader();
                reader.onload = function(){
                  term.write(decoder.decode(reader.result));
                };
                reader.readAsArrayBuffer(event.data);
            };

            socket.onclose = function (e) {
                term.write("session is close");
                window.location.reload()
            }
        }else{
            alert("connection failed"+ msg.result);
        }
}

function ws_close() {
    if(socket !== null){
        socket.close();
    }
    window.location.reload()
}
//获取主机 端口
webhost=location.hostname;
webport=location.port;

console.log(document.body.clientWidth);
cols=parseInt(document.body.clientWidth /8);
rows=parseInt(document.body.clientHeight/3);
var socket;
var term = new Terminal({
    "cursorBlink":true,
    "rows":rows,
    "cols":cols,
});

function ws_connect(){
    hostname=$("input[name=hostname]").val();
    port=$("input[name=port]").val();
    username=$("input[name=username]").val();
    password=$("#password").val();
    $.post(url="./",
        data={"hostname":hostname,"port":port,"username":username,
            "password":password,"cols":cols,"rows":rows},
        function(msg){
        if(msg.id){
            container = document.getElementById('term');
            url = 'ws://'+ webhost +':'+ webport +'/ws?id=' + msg.id;
            socket = new WebSocket(url);
            $("#term").html("");
            term.on('data', function (data) {
            //控制台输入字符
            console.log(data);
            socket.send(JSON.stringify({'data':data}));
            });

            socket.onopen = function(){
                term.open(document.getElementById('#term'), true);
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
            }

        }else{
            alert("connection failed"+ msg.result)
        }
    })

}
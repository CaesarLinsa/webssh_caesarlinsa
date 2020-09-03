
function ws_connect(e){
    $.get(url="/login", data={ "id": e.getAttribute('id')},
        function (res) {
            var dat = JSON.parse(res);
            $.ajax({
                url:"/login",
                type: "POST",
                data: {
                    "hostname": dat["hostname"],
                    "port": dat["port"],
                    "username": dat["username"],
                    "password": dat["password"]
                },
                dataType: "json",
                success: success_execute
            })
        });
}

function success_execute(msg){
        if(msg.id) {
            var url = window.location.href;
            var index = url.lastIndexOf("\/")
            var switch_url = url.substring(0,index+1) + msg.hostname + "/" + msg.id;
            window.open(switch_url);
        }
}

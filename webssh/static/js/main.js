
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
                complete: connect_callback
            })
        });
}

function connect_callback(resp){

        if(resp.status !== 200){
            alert(resp.status + ":" + resp.statusText);
            return;
        }
        var msg = resp.responseJSON;
        if(!msg.id){
            alert(msg.status);
        }
        if(msg.id)
            if(msg.id) {
                var url = window.location.href;
                var index = url.lastIndexOf("\/")
                var switch_url = url.substring(0,index+1) + msg.hostname + "/" + msg.id;
                window.open(switch_url);
            }
}

var model = $('#myModal');

//模态框打开时，触发将id放置在form中，连接id
model.on('show.bs.modal',function(event) {
     var id = $(event.relatedTarget).attr('id');
     $(".hidden").attr({"id":id});

 });

//模态框关闭时，清除文件数据及进度
model.on('hide.bs.modal',function(event) {
    $("#upload-form")[0].reset();
    $("#progress_rate").css("width", "0%");
    $("#percent").text("0%");

 });

$('#upload').click(function(event) {
    //阻止默认事件
    event.preventDefault();
    var pro = window.setInterval(function (){
    $.ajax({
        type: "POST",
        url: "/upload/progress",
        data: {"filename": $("#file").val().split("\\").pop() },
        data_type: "json",
        success: function(data) {
            var rate = data.progress * 100;
            rate = rate.toFixed(2);
            $("#progress_rate").css("width", rate + "%");
            $("#percent").text(rate + "%");
            if (rate >= 100) {
                $("#percent").text("文件上传成功！");
                window.clearInterval(pro);
            }
        }
    });
    }, 1000);
    var formData = new FormData($('#upload-form')[0]);
    var id = $(".hidden").attr("id");
    formData.append("id", id);
    $.post({
        url: '/upload',
        dataType: 'json',
        type: 'POST',
        data: formData,
        processData: false,
        cache: false,
        contentType: false,
        success: function(data) {
            if(data.status == 200){
               console.log(data);
               // $("#myModal").modal('hide');
            }else{
                alert("上传失败！" + data.result);
            }
        },
        error: function(data) {
            alert("上传失败！请确保上传文件小于5G");
        }
    })
});

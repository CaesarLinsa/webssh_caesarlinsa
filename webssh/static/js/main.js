
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

 $('#myModal').on('show.bs.modal',function(event) {
     var id = $(event.relatedTarget).attr('id');
     $(".hidden").attr({"id":id});

 });

$('#upload').click(function() {
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
            $("#myModal").modal('hide');
            if(data.status == 200){
               console.log(data);
            }else{
                alert("上传失败！" + data.result);
            }
        },
        error: function(data) {
            alert("上传失败！" + data);
        }
    })
});
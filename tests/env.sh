# env
#
reporter_port=8002
datastore_port=8003
zookeeper_port=2181
kafka_port=9092
docker_ip=$(ip -4 addr show docker0 | grep -Po 'inet \K[\d.]+')

valhalla_data_dir="valhalla_data"
